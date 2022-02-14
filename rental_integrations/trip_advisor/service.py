import hashlib
import hmac
import json
import logging
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from functools import reduce
from itertools import chain
from urllib.parse import urljoin, urlparse

from django.conf import settings
from django.utils import timezone
from requests.auth import AuthBase
from rest_framework import status

from cozmo_common.functions import deep_get
from listings.choices import CalculationMethod
from listings.models import Property, Room
from listings.serializers import PropertySerializer, ReservationSerializer
from listings.services import IsPropertyAvailable
from rental_integrations.service import RentalAPIClient
from rental_integrations.tools import strip_falsy
from rental_integrations.trip_advisor.mappings import (
    features_map,
    prop_type_map,
    revert_prop_type_map,
)
from rental_integrations.trip_advisor.service_serializers import underscoreize
from . import service_serializers as serializers

logger = logging.getLogger(__name__)


class TripAdvisorClient(RentalAPIClient):

    _base_url = settings.TRIPADVISOR_URL
    ERRORS = defaultdict(
        lambda: "Unknown validation error",
        {
            "PHOTOS": "Invalid photo links",
            "DESCRIPTION": "Description must be at least 300 characters",
            "POSTAL_CODE": "Postal Code is missing",
            "ADDRESS": "Address is missing",
            "ADDRESS_LAT_LONG_DISCREPANCY": "Address and coordinates does not match",
        },
    )

    def __init__(self, user: str, secret: str = settings.TRIPADVISOR_SECRET_KEY):
        if isinstance(secret, str):
            secret = secret.encode()
        super().__init__(user, secret)

    def get_headers(self, context):
        return {"Content-Type": "application/json"}

    def push_link(self, old_external_id, new_external_id):
        assert all([old_external_id is not None, new_external_id is not None])
        url = reduce(urljoin, [self.netloc, self._user, old_external_id, new_external_id])
        status_code, data = self._call_api(url=url, data="", http_method="get")
        if status_code == status.HTTP_200_OK:
            return data
        raise Exception(f"Push link did not work: {status_code}")

    def get_listings(self):
        """Retrieve all listings-related information."""
        url = urljoin(self.netloc, self._user)
        status_code, data = self._call_api(url=url, data="", http_method="get")
        listings_data = []
        if status_code == status.HTTP_200_OK:
            for listing in json.loads(data)[:1]:  # TODO Parallelize
                listing_path = "{}/{}".format(self._user, listing["externalListingReference"])
                listing_url = urljoin(url, listing_path)
                status_code, data = self._call_api(listing_url, "", "get")
                if status_code == status.HTTP_200_OK:
                    listings_data.append(serializers.underscoreize(json.loads(data)))

        serializer = serializers.ListingSerializer(data=listings_data, many=True)

        if not serializer.is_valid():
            logger.info("Invalid listing data: %s", serializer.errors)
            return serializer.errors
        return serializer.data

    def get_listing(self, id):
        listing_url = urljoin(self.netloc, f"{self._user}/{id}")
        status_code, data = self._call_api(listing_url, "", "get")

        if status_code == status.HTTP_200_OK:
            serializer = serializers.ListingSerializer(
                data=serializers.underscoreize(json.loads(data))
            )
            if not serializer.is_valid():
                logger.info("Invalid listing data: %s", serializer.errors)
                return serializer.errors
            return serializer.data
        return None

    def disable_listing(self, id):
        listing_url = urljoin(self.netloc, f"{self._user}/{id}")
        return self._call_api(listing_url, "", "delete")

    def push_listing(self, prop, partial=False):
        url = urljoin(self.netloc, self._user)
        listing_path = f"{self._user}/{prop.id}"
        listing_url = urljoin(url, listing_path)
        if partial:
            listing = TripParser.from_cozmo_partial(prop)
        else:
            listing = TripParser.from_cozmo(prop)
        # They are returning some validation error list
        status_code, data = self._call_api(url=listing_url, data=listing, http_method="put")

        errors = json.loads(data)
        parsed_errors = []
        if status_code == status.HTTP_400_BAD_REQUEST:
            for e in errors:
                if e.get("domain") == "ACTIVATION" and e.get("status") == "FAILURE":
                    activation_errors = {"activation": []}
                    for v in e.get("violations"):
                        error = self.ERRORS[v.get("field")]
                        activation_errors["activation"].append(error)
                    parsed_errors.append(activation_errors)
        return status_code, parsed_errors

    def get_reservations(self, listing_id: str = None):
        """Retrieve reservations of a chosen or all listings."""

    def set_listing_details(self, listing_id: str, data):
        """Set availability, pricing, or other information for a given listing."""

    @property
    def netloc(self):
        return self._base_url

    # TODO Fix interface !
    def _authenticate(self, data, headers, *, context):
        return TripAdvisorAuth(
            self._user, self._secret, data=self._parse_data(data), headers=headers, context=context
        )

    def _parse_data(self, data):
        if isinstance(data, dict):
            data = json.dumps(serializers.camelize(data))
        if isinstance(data, str):
            data = data.encode()
        return data


class TripAdvisorAuth(AuthBase):

    auth_hash = "sha512"
    algorithm = "VRS-HMAC-SHA512"

    def __init__(self, user, password, *, headers, data, context):
        self.user = user
        self.password = password
        self.headers = headers
        self.data = data
        self.context = context

    def __call__(self, r):
        http_uri = urlparse(self.context["url"])
        timestamp = timezone.now().isoformat(timespec="seconds").replace("+00:00", "Z")

        auth_data = "\n".join(
            [
                self.context["http_method"].upper(),
                http_uri.path,
                http_uri.query,
                timestamp,
                hashlib.new(self.auth_hash, self.data).hexdigest(),
            ]
        ).encode()
        data_digest = hashlib.new(self.auth_hash, auth_data).hexdigest().encode()
        hmac_signature = hmac.new(
            self.password, data_digest.lower(), digestmod=self.auth_hash
        ).hexdigest()
        r.headers["Authorization"] = "{} timestamp={}, client={}, signature={}".format(
            self.algorithm, timestamp, self.user, hmac_signature
        )

        return r


class TripParser:
    _check_time = serializers.DetailSerializer._check_time[:-1]
    _guest_requirements = (
        ("children_friendly", "CHILDREN"),
        ("smoking", "SMOKING"),
        ("pets", "PETS"),
    )

    @classmethod
    def to_cozmo(cls, data) -> dict:
        trip_advisor = underscoreize(data)
        features = defaultdict(
            lambda: False, {last: first for first, last in cls._guest_requirements}
        )
        property_type = revert_prop_type_map.get(trip_advisor["details"].get("property_type"))
        guest_requirements = {last: first for first, last in cls._guest_requirements}

        rates = trip_advisor.get("rates")
        default_rate = rates.get("default_rate")
        if trip_advisor["active"]:
            property_status = Property.Statuses.Active.name
        else:
            property_status = Property.Statuses.Draft.name

        return strip_falsy(
            {
                "status": property_status,
                "coordinates": {
                    "latitude": trip_advisor["address"]["latitude"],
                    "longitude": trip_advisor["address"]["longitude"],
                },
                "arrival_instruction": {
                    "description": trip_advisor["descriptions"].get("getting_there")
                },
                "name": trip_advisor["descriptions"].get("listing_title", "") or "(unknown name)",
                "description": trip_advisor["descriptions"].get("rental_description"),
                "rooms": [
                    *(
                        {"type": "Bathroom", "description": "Bathroom {}".format(b["ordinal"])}
                        for b in trip_advisor["details"].get("bathrooms", [])
                    ),
                    *(
                        {"type": "Bedroom", "description": "Bedroom {}".format(b["ordinal"])}
                        for b in trip_advisor["details"].get("bedrooms", [])
                    ),
                ],
                "check_in_out": {},  # TODO Calendar & reservations
                "pricing_settings": {
                    "max_guests": trip_advisor["details"].get("max_cccupancy"),
                    "nightly": default_rate.get("nightly_rate"),
                    "weekend": default_rate.get("weekend_rate"),
                },
                "property_type": property_type,
                "rental_type": "Other",
                "licence_number": trip_advisor["details"].get("tourist_license_number"),
                "location": {
                    "address": trip_advisor["address"]["address"],
                    "city": trip_advisor.get("location", {}).get("city"),
                    "country": trip_advisor.get("location", {}).get("country"),
                    "region": trip_advisor.get("location", {}).get("region"),
                    "postal_code": trip_advisor.get("address", {}).get("postal_code"),
                },
                "images": [
                    {"url": ph["url"], "caption": ph["caption"] or ""}
                    for ph in trip_advisor["photos"]
                ],
                "basic_amenities": dict(
                    chain(
                        (
                            (guest_requirements[k], True)
                            for k in trip_advisor.get("guest_requirements", [])
                            if k in guest_requirements
                        ),
                        (
                            (features[k], True)
                            for k in trip_advisor.get("features", [])
                            if k in features
                        ),
                    )
                ),
            }
        )

    @staticmethod
    def _get_rates(prop):
        try:
            default_rate = prop.pricing_settings.nightly
        except AttributeError:
            raise ValueError("Missing default rate")

        try:
            deposit = prop.pricing_settings.security_deposit
        except AttributeError:
            deposit = 0

        return {
            "rates": {
                "defaultRate": {
                    "nightlyRate": int(default_rate.nightly),
                    "weekendRate": int(default_rate.weekend),
                    "weeklyRate": int(default_rate.weekly),
                    "monthlyRate": int(default_rate.monthly),
                    "minimumStay": int(default_rate.min_stay if default_rate.min_stay < 0 else 1),
                    "additionalGuestFeeThreshold": prop.max_guests,
                    "additionalGuestFeeAmount": int(default_rate.extra_person),
                    "changeoverDay": "FLEXIBLE",  # Not supported in Cozmo
                },
                "seasonalRates": [
                    {
                        "name": "Cozmo rate {}".format(i),
                        "nightlyRate": int(rate.nightly),
                        "weekendRate": int(rate.weekend),
                        "weeklyRate": int(rate.weekly),
                        "monthlyRate": int(rate.monthly),
                        "minimumStay": int(
                            default_rate.min_stay if default_rate.min_stay < 0 else 1
                        ),
                        "additionalGuestFeeThreshold": prop.max_guests,
                        "additionalGuestFeeAmount": int(rate.extra_person),
                        "changeoverDay": "FLEXIBLE",  # Not supported in Cozmo
                        "startDate": str(rate.time_frame.lower),
                        "endDate": str(rate.time_frame.upper),
                    }
                    for i, rate in enumerate(
                        prop.rate_set.exclude(time_frame=(None, None)).exclude(seasonal=False),
                        start=1,
                    )
                ],
                "weekendType": "SATURDAY_SUNDAY",  # Not supported in Cozmo
                "damageDeposit": str(deposit),  # TODO Might be percentage
                "taxPercentage": "1",  # FIXME Hardcoded value
            }
        }

    @staticmethod
    def _get_fees(prop):
        queryset = prop.additionalfee_set.filter(
            calculation_method=CalculationMethod.Per_Stay.value, optional=False, refundable=False
        )
        return {"fees": [{"name": fee.name, "amount": str(fee.value)} for fee in queryset]}

    @staticmethod
    def _get_blocked_days(prop):
        today = date.today()
        ipa = IsPropertyAvailable(prop, today, today + timedelta(days=360))
        ipa.run_check()

        return {
            "calendar": {
                "bookedRanges": [
                    {"start": str(r["start_date"]), "end": str(r["end_date"])}
                    for r in ipa.blocked_days
                ]
            }
        }

    @classmethod
    def _get_details(cls, prop_data):
        def get_time(dict, *keys):
            time = deep_get(dict, keys)
            return cls._check_time(int(time.split(":")[0])) if time else None

        def get_bathrooms():
            bathrooms = [
                b for b in prop_data["rooms"] if b["type"] == Room.Types.Bathroom.pretty_name
            ]
            prop_bathrooms = Decimal(prop_data["bathrooms"])
            if len(bathrooms) < prop_bathrooms:
                return [{"bathroomType": "NONE"} for _ in range(int(prop_bathrooms))]
            return [{"bathroomType": "NONE"} for _ in range(len(bathrooms))]

        def get_bedrooms():
            def map_bed(bed):
                beds = Room.Beds
                return {
                    beds.Crib.pretty_name: "COT_BED",
                    beds.Double.pretty_name: "KING_BED",
                    beds.King.pretty_name: "SUPER_KING_BED",
                    beds.Other.pretty_name: "SOFA_BED",
                    beds.Queen.pretty_name: "KING_BED",
                    beds.Single.pretty_name: "SINGLE_BED",
                    beds.Twin.pretty_name: "DOUBLE_BED",
                    beds.Bunk.pretty_name: "BUNK_BED",
                }.get(bed)

            bedrooms = [
                b for b in prop_data["rooms"] if b["type"] == Room.Types.Bedroom.pretty_name
            ]
            if bedrooms:
                return [
                    {"beds": map_bed(bed) for bed in b.beds if bed != Room.Beds.No_Bed.pretty_name}
                    for b in bedrooms
                ]
            else:
                return [{"beds": []} for _ in range(int(Decimal(prop_data["bedrooms"])))]

        return {
            "details": {
                "bathrooms": get_bathrooms(),
                "bedrooms": get_bedrooms(),
                "carRequired": "NOT_REQUIRED",  # Not supported in Cozmo
                "checkInTime": get_time(prop_data, "check_in_out", "check_in_to"),
                "checkOutTime": get_time(prop_data, "check_in_out", "check_out_until"),
                "maxOccupancy": prop_data.get("max_guests"),
                "propertyType": prop_type_map.get(prop_data["property_type"], "Other"),
                "touristLicenseNumber": prop_data["license_number"] or None,
            }
        }

    @classmethod
    def from_cozmo_partial(cls, prop: Property) -> dict:
        """This method returns just Rates, Fees and Blocking"""

        # active is required even on update
        return {
            "active": prop.status == Property.Statuses.Active.value,
            **cls._get_blocked_days(prop),
            **cls._get_fees(prop),
            **cls._get_rates(prop),
        }

    @classmethod
    def from_cozmo(cls, prop: Property) -> dict:
        prop_data = PropertySerializer(instance=prop).data
        prop_data["reservations"] = ReservationSerializer(
            instance=prop.reservation_set.all(), many=True
        ).data
        guest_requirements = dict(cls._guest_requirements)
        return {
            "active": prop_data["status"] == Property.Statuses.Active.pretty_name,
            "address": {
                "address": prop_data["address"],
                "latitude": prop_data["coordinates"]["latitude"],
                "longitude": prop_data["coordinates"]["longitude"],
                "postalCode": prop_data["location"]["postal_code"],
                "showExactAddress": True,
            },
            "currency": prop_data.get("currency"),
            "descriptions": {
                "describeTheArea": None,
                "describeTheDestination": None,
                "furtherDetails": None,
                "furtherDetailsIndoors": None,
                "furtherDetailsOutdoors": None,
                "gettingThere": deep_get(prop_data, "arrival_instruction", "description"),
                "listingTitle": prop_data["name"],
                "rentalDescription": prop_data["description"],
                "searchSummary": None,
            },
            **cls._get_details(prop_data),
            "features": [
                features_map[f.get("name")]
                for f in prop_data["features"]
                if f.get("name") in features_map
            ],
            "guestRequirements": [
                v for k, v in guest_requirements.items() if prop_data["basic_amenities"].get("k")
            ],
            "location": {
                "city": deep_get(prop_data, "location", "city"),
                "country": deep_get(prop_data, "location", "country"),
                "countryCode": None,
                "region": deep_get(prop_data, "location", "region"),
            },
            "photos": [
                {
                    "url": i["url"],
                    "caption": i["caption"],
                    "externalPhotoReference": "{id}. {caption}".format(**i),
                }
                for i in prop_data["images"]
            ],
            "textLanguage": "en_US",
            "nearbyAmenities": [],  # TODO Is it possible?
            **cls._get_blocked_days(prop),
            **cls._get_fees(prop),
            **cls._get_rates(prop),
        }

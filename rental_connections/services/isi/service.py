from functools import partial
from itertools import chain
from logging import getLogger
from operator import itemgetter
from typing import NamedTuple, Optional
from urllib.parse import quote

from zeep import Client as ZeepClient
from zeep.exceptions import Fault
from zeep.helpers import serialize_object

from cozmo_common.functions import deep_get
from listings.choices import Currencies, Rentals
from rental_integrations.exceptions import ServiceException
from rental_integrations.service import RentalAPIClient
from rental_integrations.tools import strip_falsy
from . import mappings

logger = getLogger(__name__)

url_quote = partial(quote, safe=";/?:@&=+$,")


ReservationDetails = NamedTuple(
    "ReservationDetails",
    [
        ("check_in", "datetime.date"),
        ("check_out", "datetime.date"),
        ("adults", int),
        ("children", int),
        ("pets", Optional[int]),
    ],
)


Address = NamedTuple(
    "Address",
    [
        ("address", str),
        ("city", str),
        ("province", str),
        ("postal_code", str),
        ("country_code", str),
        ("phone", str),
    ],
)


Guest = NamedTuple(
    "Guest", [("first_name", str), ("last_name", str), ("email", str), ("address", Address)]
)


class IsiService(RentalAPIClient):

    features_map = mappings.features_map
    property_types_map = mappings.property_types_map
    _startup_info = {}

    def __init__(self, user, secret, company_id):
        super().__init__(user, secret)
        self._auth = {"strUserId": self._user, "strPassword": self._secret, "strCOID": company_id}
        self._company_id = company_id
        self._client = ZeepClient(self.netloc)
        self._contract_info = None

    def _authenticate(self, data, deprecated_coid=False):
        data.update(self._auth)
        if deprecated_coid:
            data["strCoId"] = data.pop("strCOID")
        return data

    def _call_api(self, method_name, data):
        try:
            resp = self._parse_data(getattr(self._client.service, method_name)(**data))
        except AttributeError as e:
            raise ValueError("No such method: {}".format(method_name)) from e
        except Fault as e:
            raise ServiceException(*e.args) from e
        return resp

    def _parse_data(self, data):
        return serialize_object(data)

    def _get_listings_details(self, listing_ids, include_blockings=True):
        """
        Fetch details of chosen listings.

        Args:
            listing_ids (typing.Iterable): ids of listings
            include_blockings (bool): whether or not to retrieve non-availability array

        Returns:
            list[dict]: listings details
        """
        data = self._authenticate(
            {"strPropId": ",".join(listing_ids), "blnSendNonAvail": include_blockings}
        )
        return self._call_api("getPropertyDesc", data)

    @property
    def contract_info(self):
        if self._contract_info is None:
            self._contract_info = self._call_api(
                "getReservationContractInfo", self._authenticate({})
            )
        return self._contract_info

    def to_cozmo_property(self, listing) -> dict:
        def safe_int(value):
            try:
                ret = int(value)
            except (ValueError, TypeError):
                ret = 1
            return ret

        def safe_currency(code):
            try:
                currency = Currencies(code).pretty_name
            except ValueError:
                currency = None
            return currency

        prop = dict(
            external_id=listing.get("strPropId"),
            name=(listing.get("strName") or "")[:100],
            property_type=self.get_property_type(listing.get("strType")),
            rental_type=Rentals.Entire_Home.pretty_name,
            max_guests=listing.get("intOccu"),
            bedrooms=int(listing.get("dblBeds") or 0),
            bathrooms=int(listing.get("dblBaths") or 0),
            descriptions=dict(
                headline=(listing.get("strPropertyHeadLine") or "")[:150],
                description=listing.get("strDesc", ""),
            ),
            location=dict(
                country=listing.get("strCountry") or "",
                region=listing.get("strState") or "",
                city=listing.get("strCity") or "",
                address=listing.get("strAddress1", ""),
                apartment=listing.get("strAddress2", ""),
                postal_code=listing.get("strZip"),
            ),
            check_in_out=dict(
                check_in_to=":".join((self.contract_info["strCheckInTime"] or "").split(":")[:2])
                or None,
                check_out_until=":".join(
                    (self.contract_info["strCheckOutTime"] or "").split(":")[:2]
                )
                or None,
            ),
            coordinates=dict(
                longitude=round(listing.get("dblLongitude", 0), 12),
                latitude=round(listing.get("dblLatitude", 0), 12),
            ),
            features=list(
                chain(
                    (
                        {"name": n, "value": safe_int(v or 0)}
                        for n, v in zip(
                            deep_get(listing, "arrAttributes", "string") or [],
                            deep_get(listing, "arrAttributeValues", "string") or [],
                        )
                    ),
                    (
                        {"name": am["strName"], "value": safe_int(am["strValue"] or 0)}
                        for am in deep_get(listing, "arrPropertyAmenities", "clsPropertyAmenity")
                        or []
                    ),
                )
            ),
            images=[
                {
                    "caption": ph.get("caption") or ph.get("strImageName", "") or "",
                    "url": url_quote(ph.get("strURL")),
                }
                for ph in deep_get(listing, "arrPicList", "clsPictureInfo") or []
                if ph.get("strURL", "").startswith("http")
            ],
            videos=[
                {
                    "caption": ph.get("caption") or ph.get("strVideoName") or "",
                    "url": url_quote(ph.get("strURL")),
                }
                for ph in deep_get(listing, "arrVideoList", "clsVideoInfo") or []
                if ph.get("strURL", "").startswith("http")
            ],
            availabilities=[
                {
                    "min_stay": nights.get("intMinNights", 0),
                    "time_frame": {
                        "lower": nights["dtBeginDate"].date(),
                        "upper": nights["dtEndDate"].date(),
                    },
                }
                for nights in deep_get(listing, "arrMinNightsInfo", "clsMinNightsInfo") or []
            ],
            availability_settings={
                "min_stay": self._startup_info.get("intMinStay", 0),
                "max_stay": self._startup_info.get("intMaxstay", 0),
            },
            pricing_settings={"included_guests": listing.get("intOccu"), "nightly": 0},
            rates=[
                {
                    "nightly": rate.get("dblRate", 0),
                    "time_frame": {
                        "lower": rate["dtBeginDate"].date(),
                        "upper": rate["dtEndDate"].date(),
                    },
                }
                for rate in deep_get(listing, "arrSeasonRates", "clsSeasonRates") or []
            ],
            currency=safe_currency(listing.get("strCurrencyCode", "USD")),
            turn_days=[
                {
                    "time_frame": {
                        "lower": td["dtBeginDate"].date(),
                        "upper": td["dtEndDate"].date(),
                    },
                    "days": [day - 1 for day in td["arrTurnDays"]["int"]],
                }
                for td in deep_get(listing.get, "arrTurnDayInfo", "clsTurnDay") or []
            ],
        )
        if self._startup_info.get("dblMinRent"):
            prop["pricing_settings"]["nightly"] = self._startup_info.get("dblMinRent")
        return strip_falsy(prop)

    @property
    def netloc(self):
        return "https://secure.instantsoftwareonline.com/StayUSA/ChannelPartners/wsWeblinkPlusAPI.asmx?wsdl"  # noqa: E501

    def get_listing(self, listing_id):
        """
        Fetch details of chosen listing.

        Args:
            listing_id (typing.Iterable): id of a listing

        Returns:
            dict: listing details
        """
        try:
            listing = self._get_listings_details((listing_id,))[0]
            self._get_startup_info()
        except TypeError:
            listing = None
        return listing

    def get_listings(self, sort_by=None):
        sort_mapping = {"listing_id": "prop_id", "name": "name", None: None}
        try:
            sort_by = sort_mapping[sort_by]
        except KeyError:
            raise ValueError('Incorrect value for "sort_by"')

        data = self._authenticate({"strSortBy": sort_by})
        ids = map(itemgetter("strId"), self._call_api("getPropertyIndexes", data))
        self._get_startup_info()
        return self._get_listings_details(ids)

    def get_listings_count(self):
        data = self._authenticate({})
        return len(self._call_api("getPropertyIndexes", data))

    def set_listing_details(self):
        pass

    def get_reservations(self, listing_id, detailed=False):
        """
        Fetch reservations of chosen listing.

        If `detailed` is set to `True` but there are missing permissions for fetching detailed
        data, simple data will be returned.

        Args:
            detailed (bool): whether or not try to fetch detailed reservation data

        Returns:
            list: simple or detailed reservations data
        """
        data = self._authenticate({"strPropID": listing_id})
        reservations = self._call_api("getPropertyAvailabilityInfo", data)

        if detailed:
            details_data = self._authenticate(
                {"arrQuoteNumbers": list(map(itemgetter("intQuoteNum"), reservations))}
            )
            detailed_reservations = self._call_api("getReservationDetailsMultiple", details_data)
            reservations = detailed_reservations or reservations

        blockings = [
            (res["dtFromDate"].date(), res["dtToDate"].date()) for res in reservations or []
        ]
        return blockings

    def create_reservation(self, listing_id, reservation: ReservationDetails, guest: Guest):
        optional_query = {"intPets": reservation.pets} if reservation.pets else {}
        query = self.call(
            "getReservationQuery",
            {
                "objResQueryInfo": self._authenticate(
                    {
                        "strCheckIn": reservation.check_in.isoformat(),
                        "intNights": (reservation.check_out - reservation.check_in).days,
                        "strProperty": listing_id,
                        "intAdults": reservation.adults,
                        "intChildren": reservation.children,
                        **optional_query,
                    }
                )
            },
        )

        if guest.address.country == "US":
            address_province = {"strState": guest.address.province}
        else:
            address_province = {"strProvince": guest.address.province}

        reservation = self._client.service.createBooking(
            objBookingRequest={
                "strCOID": self._company_id,
                "dtCheckIn": reservation.check_in,
                "intNights": (reservation.check_out - reservation.check_in).days,
                "strProperty": listing_id,
                "intAdults": reservation.adults,
                "intChildren": reservation.children,
                "objGuestDetails": {
                    "strFirstName": guest.first_name,
                    "strLastName": guest.last_name,
                    "strEmail": guest.email,
                    "objAddress": {
                        "strAddress1": guest.address.address,
                        "strCity": guest.address.city,
                        "strZip": guest.address.postal_code,
                        "strCountry": guest.address.country_code,
                        "strHomePhone": guest.address.phone,
                        **address_province,
                    },
                },
                "blnAcceptCSA": False,
                "dblCCAmount": query["dblDues"],
                # Currently not supported:
                # 'objCreditCardDetails': '',
                # 'objTravelerPreferences': '',
                # 'objServiceFee': '',
            },
            _soapheaders={
                "clsPartnerAuthentication": {"strUserID": self._user, "strPassword": self._secret}
            },
        )

        return reservation

    def get_updates(self, minutes=60):
        changelog = self._call_api(
            "getChangeLogInfo",
            self._authenticate(
                {"strChangeLogOption": "AVAILABILITY,PRICING,PROPERTY", "intMinutes": minutes},
                deprecated_coid=True,
            ),
        )

        grouped_changelog = {}
        for log in changelog or []:
            grouped_changelog.setdefault(log["strChangeLog"], []).append(log)

        get_reservation_changelog = partial(self._call_api, "getReservationChangeLog")

        grouped_changelog["Availability"] = [
            avail["body"]["getReservationChangeLogResult"]["clsResChangeLogInfo"]
            for avail in map(
                get_reservation_changelog,
                (
                    self._authenticate(
                        {
                            "strPropID": prop["strPropId"],
                            "intMinutes": minutes,
                            "strOptions": "ALL",
                            "intLogID": 0,
                            "intMaxRows": 1000,
                        }
                    )
                    for prop in grouped_changelog.get("Property", [])
                ),
            )
            if avail["body"]["getReservationChangeLogResult"] is not None
        ]

        return grouped_changelog

    def perform_check_request(self):
        try:
            self._call_api("getCustomerInfo", self._authenticate({}))
        except ServiceException:
            return False
        return True

    def _get_startup_info(self):
        """Endpoint which returns info about Rates and Availabilities"""
        self._startup_info = self._call_api("getStartupInfo", self._authenticate({}))

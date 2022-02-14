from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import partial
from itertools import chain, groupby
from logging import getLogger
from urllib.parse import quote

from zeep import Client as ZeepClient
from zeep.exceptions import Fault
from zeep.helpers import serialize_object

from listings.choices import Rentals
from rental_integrations.exceptions import ServiceException
from rental_integrations.service import RentalAPIClient
from rental_integrations.tools import strip_falsy
from . import mappings

logger = getLogger(__name__)

url_quote = partial(quote, safe=";/?:@&=+$,")


class EscapiaService(RentalAPIClient):
    property_types_map = mappings.property_types_map

    def __init__(self, user, secret, *args):
        super().__init__(user, secret)
        self._api_version = 1.030
        self._auth = {
            "Version": self._api_version,
            "POS": {
                "Source": {"RequestorID": {"ID": self._user, "MessagePassword": self._secret}}
            },
        }
        self._client = ZeepClient(self.netloc)

    @property
    def netloc(self):
        return "https://api.escapia.com/EVRNService.svc?wsdl"

    def _authenticate(self, data):
        data.update(self._auth)
        return data

    def _call_api(self, method_name, data):
        try:
            resp = self._parse_data(getattr(self._client.service, method_name)(**data))
        except AttributeError as e:
            raise ValueError("No such method: {}".format(method_name)) from e
        except Fault as e:
            logger.info(e)
            resp = None
        return resp

    def _parse_data(self, data):
        try:
            status, *parsed = data._value_1
            if "Errors" in status:
                raise ServiceException(status["Errors"].Error[0])
            elif "Success" not in status:
                raise ServiceException(status)
            parsed_data = parsed[0]
        except (AttributeError, IndexError):
            logger.warning("Unexpected response from Escapia")
            parsed_data = None

        return serialize_object(parsed_data)

    def to_cozmo_property(self, listing) -> dict:
        property_type = listing["UnitInfo"]["CategoryCodes"]["UnitCategory"][0]["CodeDetail"]
        multimedia = listing["UnitInfo"]["Descriptions"]["MultimediaDescriptions"][
            "MultimediaDescription"
        ]  # noqa: E501

        rate_mapping = {
            "Nightly": "nightly",
            "Weekend": "weekend",
            "Midweek": "weekly",
            "Weekly": "weekly",
            "Monthly": "monthly",
        }
        turn_days = dict(zip(("Mon", "Tue", "Weds", "Thur", "Fri", "Sat", "Sun"), range(7)))

        prop = dict(
            external_id=listing["UnitCode"],
            name=listing["UnitInfo"]["UnitName"]["_value_1"],
            descriptions=dict(
                headline=listing["UnitHeadline"],
                description=listing["UnitInfo"]["Descriptions"]["DescriptiveText"],
            ),
            location=dict(
                country=listing["UnitInfo"]["Address"]["CountryName"]["Code"] or "",
                region=listing["UnitInfo"]["Address"]["StateProv"]["StateCode"] or "",
                city=listing["UnitInfo"]["Address"]["CityName"] or "",
                address=" ".join(listing["UnitInfo"]["Address"]["AddressLine"] or []),
                postal_code=listing["UnitInfo"]["Address"]["PostalCode"],
            ),
            pricing_settings=dict(max_guests=listing["UnitInfo"]["MaxOccupancy"], nightly=0),
            property_type=self.get_property_type(property_type),
            rental_type=Rentals.Entire_Home.pretty_name,
            area=listing["UnitInfo"]["AreaSquareFeet"],
            **{  # bedrooms and bathrooms count
                r["CodeDetail"].lower(): "{:.1f}".format(r["Quantity"])
                for r in listing["UnitInfo"]["CategoryCodes"]["RoomInfo"]
            },
            check_in_out=dict(
                check_in_to=listing["Policies"]["Policy"][0]["PolicyInfo"]["CheckInTime"],
                check_out_until=listing["Policies"]["Policy"][0]["PolicyInfo"]["CheckOutTime"],
            ),
            coordinates=dict(
                longitude=listing["UnitInfo"]["Position"]["Longitude"],
                latitude=listing["UnitInfo"]["Position"]["Latitude"],
            ),
            arrival_instruction=dict(),
            features=list(),
            images=[
                {
                    "url": url_quote(i["ImageFormat"][0]["URL"]),
                    "caption": i["Description"][0]["Caption"],
                }
                for i in chain.from_iterable(
                    images["ImageItems"]["ImageItem"]
                    for images in multimedia
                    if images["ImageItems"] is not None
                )
                if i["ImageFormat"][0]["URL"].startswith("http")
            ],
            videos=[
                {"url": url_quote(v["VideoFormat"][0]["URL"]), "caption": v["Caption"] or ""}
                for v in chain.from_iterable(
                    videos["VideoItems"]["VideoItem"]
                    for videos in multimedia
                    if videos["VideoItems"] is not None
                )
                if v["VideoFormat"][0]["URL"].startswith("http")
            ],
            availabilities=[],
            rates=[
                {
                    "label": rate["SeasonName"],
                    "nightly": 0,
                    rate_mapping[rate["RateType"]]: next(
                        round(Decimal(price), 2)
                        for price in (rate["FixedRate"], rate["MaxRate"], rate["MinRate"])
                        if price
                    ),
                    "time_frame": {
                        "lower": datetime.strptime(rate["Start"], "%m/%d/%Y").date().isoformat(),
                        "upper": datetime.strptime(rate["End"], "%m/%d/%Y").date().isoformat(),
                    },
                }
                for rate in listing["UnitInfo"]["RateRanges"]["RateRange"]
            ],
            turn_days=[
                {
                    "time_frame": {
                        "lower": datetime.strptime(rate["Start"], "%m/%d/%Y").date().isoformat(),
                        "upper": datetime.strptime(rate["End"], "%m/%d/%Y").date().isoformat(),
                    },
                    "days": [
                        turn_days[day] for day in turn_days.keys() if rate["StayRequirement"][day]
                    ],
                }
                for rate in listing["UnitInfo"]["RateRanges"]["RateRange"]
            ],
        )
        return strip_falsy(prop)

    def get_listings(self):
        """
        Fetch details of all listings.

        Returns:
            list[dict]: details of listings
        """
        data = self._authenticate(
            {"Criteria": {"Criterion": {"Region": {"CountryCode": "US"}}}, "MaxResponses": 10000}
        )
        try:
            search_results = self._call_api("UnitSearch", data)["Units"]["Unit"]
        except (TypeError, KeyError, AttributeError):
            logger.warning("Unexpected response from Escapia")
            search_results = []

        try:
            unit_ids = [{"UnitCode": uc["UnitCode"]} for uc in search_results]
            listings = self._call_api(
                "UnitDescriptiveInfo",
                self._authenticate({"UnitDescriptiveInfos": {"UnitDescriptiveInfo": unit_ids}}),
            )["UnitDescriptiveContents"]["UnitDescriptiveContent"]
        except (TypeError, KeyError, AttributeError):
            listings = None
        return listings

    def get_listings_count(self):
        data = self._authenticate(
            {"Criteria": {"Criterion": {"Region": {"CountryCode": "US"}}}, "MaxResponses": 10000}
        )
        try:
            search_results = self._call_api("UnitSearch", data)["Units"]["Unit"]
        except (TypeError, KeyError, AttributeError):
            logger.warning("Unexpected response from Escapia")
            search_results = []

        return len(search_results)

    def get_listing(self, listing_id):
        """
        Fetch details of chosen listing.

        Args:
            listing_id (str): id of a listing

        Returns:
            dict: listing details
        """
        return self._call_api(
            "UnitDescriptiveInfo",
            self._authenticate(
                {"UnitDescriptiveInfos": {"UnitDescriptiveInfo": {"UnitCode": listing_id}}}
            ),
        )["UnitDescriptiveContents"]["UnitDescriptiveContent"][0]

    def get_reservations(self, listing_id, detailed=False):
        """
        Fetch reservations of chosen listing.

        Returns:
            list: reservations data
        """
        max_days = 764
        look_back = 60
        today = date.today()
        start_date = today - timedelta(look_back)
        end_date = today + timedelta(max_days - look_back - 1)
        data = self._call_api(
            "UnitCalendarAvail",
            self._authenticate(
                {
                    "UnitRef": {"UnitCode": listing_id},
                    "CalendarDateRange": {"Start": start_date, "End": end_date},
                }
            ),
        )

        try:
            cal = data["UnitCalendarAvailSegments"]["UnitCalendarAvailSegment"][0]
        except (IndexError, KeyError):
            cal = defaultdict(list)

        availability_mark = "A"
        blockings = []
        current_day = start_date
        for avail, days in groupby(cal["DailyAvailability"]):
            if avail != availability_mark:
                days_delta = timedelta(sum(1 for _ in days))
                blockings.append((current_day, current_day + days_delta))
                current_day += days_delta

        return blockings

    def set_listing_details(self):
        pass

    def perform_check_request(self):
        data = self._authenticate(
            {"Criteria": {"Criterion": {"Region": {"CountryCode": "XX"}}}, "MaxResponses": 1}
        )
        return self._call_api("UnitSearch", data) is not None

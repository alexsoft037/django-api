import json
import logging
import mimetypes
import urllib
from base64 import b64encode
from collections import defaultdict
from contextlib import suppress
from datetime import datetime, timedelta
from functools import partial
from multiprocessing import cpu_count
from multiprocessing.dummy import Pool as ThreadPool
from typing import Iterable

from django.conf import settings
from django.db.models.functions import Greatest, Least, Lower, Upper
from django.utils import timezone
from rest_framework import status

from app_marketplace.choices import AirbnbSyncCategory
from app_marketplace.exceptions import ServiceError
from cozmo_common.throttling import RateLimit, ThrottlingError, check_throttling
from listings.choices import CalculationMethod, WeekDays
from listings.models import (
    BookingSettings,
    CheckInOut,
    ListingDescriptions,
    PricingSettings,
    Room,
    Suitability,
)
from rental_integrations.airbnb import choices
from rental_integrations.airbnb.constants import DEFAULT_LOCALE
from rental_integrations.airbnb.utils import to_cozmo_reservation
from rental_integrations.service import RentalAPIClient
from . import mappings
from .choices import Amenity, AmountType, CancellationPolicy, StatusCategory

logger = logging.getLogger(__name__)


def _additional_fees(**fees):
    return [{"fee_tax_type": name, **value} for name, value in fees.items() if value["value"]]


def _check_in_out(check_in, check_in_ends, check_out):
    def flexible_or_hour(time):
        if time.upper() in ["FLEXIBLE", "NOT_SELECTED"]:
            time = ""
        else:
            time = "{:02d}".format(int(time)) + ":00"
        return time

    return {
        "check_in_from": flexible_or_hour(str(check_in)) if check_in else "",
        "check_in_to": flexible_or_hour(str(check_in_ends)) if check_in_ends else "",
        "check_out_until": flexible_or_hour(str(check_out)) if check_out else "",
    }


def SecurityDepositTypes(args):
    pass


class AirbnbService(RentalAPIClient):
    features_map = {}
    property_types_map = {}
    throttles = {
        "origin_ip": {
            RateLimit("airbnb:ip_10sec", timedelta(seconds=10), max_calls=200),
            RateLimit("airbnb:ip_5min", timedelta(minutes=5), max_calls=2500),
            RateLimit("airbnb:ip_1hour", timedelta(hours=1), max_calls=20000),
            RateLimit("airbnb:ip_1day", timedelta(days=1), max_calls=200_000),
        },
        "endpoints": {
            "/authorizations": {
                RateLimit("airbnb:authorizations_1hour", timedelta(hours=1), max_calls=1000)
            },
            "/listing_photos": {
                RateLimit("airbnb:listing_photos_1hour", timedelta(hours=1), max_calls=50000)
            },
            "/calendar_operations": {
                RateLimit("airbnb:calendar_oprations_1min", timedelta(minutes=1), max_calls=160)
            },
            "/messages": {RateLimit("airbnb:messages_1min", timedelta(minutes=1), max_calls=50)},
            "/threads": {RateLimit("airbnb:threads_1min", timedelta(minutes=1), max_calls=200)},
        },
    }

    def get_headers(self, context):
        return {
            "X-Airbnb-API-Key": settings.AIRBNB_SECRET,
            "X-Airbnb-OAuth-Token": self._secret,
            "Content-Type": "application/json",
        }

    @property
    def netloc(self):
        return "https://api.airbnb.com/v2/"

    def _call_api(self, url, data, http_method):
        throttles = self._get_throttles(url)

        try:
            with check_throttling(throttles):
                return super()._call_api(url, data, http_method)
        except ThrottlingError as e:
            logger.warn("Airbnb hit rate limit")
            raise e

    def _get_throttles(self, url):
        try:
            path = urllib.parse.urlparse(url).path
            ep_throttles = next(
                throttles
                for fragment, throttles in self.throttles["endpoints"].items()
                if fragment in path
            )
        except StopIteration:
            ep_throttles = {
                RateLimit(f"airbnb:{path}_10sec", timedelta(seconds=10), max_calls=100),
                RateLimit(f"airbnb:{path}_5min", timedelta(minutes=5), max_calls=1250),
                RateLimit(f"airbnb:{path}_1hour", timedelta(hours=1), max_calls=7500),
                RateLimit(f"airbnb:{path}_1day", timedelta(days=1), max_calls=90000),
            }

        user_throttles = {
            RateLimit(f"airbnb:{self._user}_1hour", timedelta(hours=1), max_calls=2000)
        }
        throttles = user_throttles | self.throttles["origin_ip"] | ep_throttles
        return throttles

    def get_me_user(self):
        url = urllib.parse.urljoin(self.netloc, f"users/me")
        status_code, content = self._call_api(url, {}, "get")
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["user"]
        return result or dict()

    def push_listing_status(self, listing_id: str, active: bool):
        data = dict(has_availability=active)
        url = urllib.parse.urljoin(self.netloc, f"listings/{listing_id}")
        status_code, content = self._call_api(url, data, "put")
        result = dict()
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["listing"]
        return result

    def push_listing_review_and_status(self, listing_id: str, active: bool):
        """
        WARNING: This function is deprecated and is still here to remind that has_availability
        can only be set when the status has been set to ready_to_review and approved.
        has_availability should be set when the webhook notification has been received
        """
        data = dict(
            has_availability=active,
            requested_approval_status_category=StatusCategory.ready_for_review.pretty_name,
        )
        url = urllib.parse.urljoin(self.netloc, f"listings/{listing_id}")
        status_code, content = self._call_api(url, data, "put")
        result = dict()
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["listing"]
        return result

    def get_detailed_listing(self, listing_id: str) -> dict:
        listing = self.get_listing(listing_id)
        listing["extras"] = {
            "descriptions": self.get_detailed_descriptions(listing_id),
            "photos": self.get_photos(listing_id),
            "listing_rooms": self.get_listing_rooms(listing_id),
            "booking_settings": self.get_booking_settings(listing_id),
            "availability_rules": self.get_availability_rules(listing_id),
            "pricing_settings": self.get_pricing_settings(listing_id),
        }
        return listing

    def get_detailed_descriptions(self, listing_id: str, locale: str = "en") -> dict:
        url = urllib.parse.urljoin(self.netloc, f"listing_descriptions/{listing_id}/{locale}")
        status_code, content = self._call_api(url, {}, "get")
        result = dict()
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["listing_description"]
        return result

    def get_listing(self, listing_id: str) -> dict:
        url = urllib.parse.urljoin(self.netloc, f"listings/{listing_id}")
        status_code, content = self._call_api(url, {}, "get")
        if status_code == status.HTTP_200_OK:
            listing = json.loads(content)["listing"]
        else:
            listing = {}
        return listing

    def get_listing_room(self, listing_id: str, room_id: str) -> dict:
        url = urllib.parse.urljoin(self.netloc, f"listing_rooms/{listing_id}/{room_id}")
        status_code, content = self._call_api(url, {}, "get")
        result = dict()
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["listing_room"]
        return result

    def get_listing_rooms(self, listing_id: str) -> list:
        url = urllib.parse.urljoin(self.netloc, f"listing_rooms/?listing_id={listing_id}")
        status_code, content = self._call_api(url, {}, "get")
        result = list()
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["listing_rooms"]
        return result

    def get_booking_settings(self, listing_id: str) -> dict:
        url = urllib.parse.urljoin(self.netloc, f"booking_settings/{listing_id}")
        status_code, content = self._call_api(url, {}, "get")
        result = dict()
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["booking_setting"]
        return result

    def get_availability_rules(self, listing_id: str) -> dict:
        url = urllib.parse.urljoin(self.netloc, f"availability_rules/{listing_id}")
        status_code, content = self._call_api(url, {}, "get")
        result = dict()
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["availability_rule"]
        return result

    def get_pricing_settings(self, listing_id: str) -> dict:
        url = urllib.parse.urljoin(self.netloc, f"pricing_settings/{listing_id}")
        status_code, content = self._call_api(url, {}, "get")
        result = dict()
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["pricing_setting"]
        return result

    def get_calendar_range(self, listing_id: str, start_date: str, end_date: str):
        url = urllib.parse.urljoin(self.netloc, f"calendars/{listing_id}/{start_date}/{end_date}")
        status_code, content = self._call_api(url, {}, "get")
        result = dict()
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["calendar"]
        return result

    def push_calendar_range(self, listing_id: str, start_date: str, end_date: str, rule: dict):
        url = urllib.parse.urljoin(self.netloc, f"calendars/{listing_id}/{start_date}/{end_date}")
        status_code, content = self._call_api(url, rule, "put")
        if status_code == status.HTTP_200_OK:
            return json.loads(content)["calendar"]
        raise ServiceError(
            f"Unable to push calendar range for {listing_id}. status_code={status_code}"
        )

    def _get_listings_query_params(self, limit, offset):
        query_params = {
            "user_id": self._user,
            "has_availability": False,
            "exclude_active": False,
            "exclude_cohosted_listings": False,
            "_limit": limit,
            "_offset": offset,
        }
        return query_params

    def _get_listings_count(self):
        url = urllib.parse.urljoin(self.netloc, "listings")
        offset = 0
        limit = 0
        params = urllib.parse.urlencode(self._get_listings_query_params(limit, offset))
        status_code, content = self._call_api(f"{url}?{params}", {}, "get")
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["metadata"]
            record_count = result["record_count"]
            listing_count = result["listing_count"]
            if record_count != listing_count:
                logger.warning(
                    f"record_count != listing_count ({record_count} != {listing_count})\
                 when fetching _get_listing_count"
                )
            return listing_count
        raise ServiceError("Unable to fetch listing count, status={}".format(status_code))

    def get_listings(self):
        base_url = urllib.parse.urljoin(self.netloc, "listings")
        listing_count = self._get_listings_count()

        offset = 0
        limit = 50
        fetch_listing_jobs = list()
        while (offset == 0) or offset < listing_count:
            params = urllib.parse.urlencode(self._get_listings_query_params(limit, offset))
            url = f"{base_url}?{params}"
            fetch_listing_jobs.append(url)
            offset += limit

        get_listings_with_offset = partial(self._call_api, data={}, http_method="get")
        with ThreadPool(cpu_count()) as pool:
            responses = pool.map(get_listings_with_offset, fetch_listing_jobs)

        listings = list()
        for status_code, response in responses:
            if status_code == status.HTTP_200_OK:
                new_listings = json.loads(response)["listings"]
                listings.extend(new_listings)
            else:
                logger.error("Not able to retrieve listings, status={}".format(status_code))

        return listings

        # all_photos = []
        # with ThreadPool(cpu_count()) as pool:
        #     photos_url = urllib.parse.urljoin(self.netloc, "listing_photos/?listing_id={}")
        #     images_args = (
        #         (photos_url.format(listing["id"]), {}, "get")
        #         for listing in listings
        #         if "id" in listing
        #     )
        #     all_photos = pool.starmap(self._call_api, images_args)

        # if not all_photos:
        #     logger.info("No Airbnb photos fetched")
        #     for listing in listings:
        #         listing["photos"] = list()
        # else:
        #     for listing, (status_code, photos) in zip(listings, all_photos):
        #         if status_code == status.HTTP_200_OK:
        #             listing["photos"] = json.loads(photos)["listing_photos"]

        # return listings

    def push_message(self, thread_id: int, message: str):
        url = urllib.parse.urljoin(self.netloc, "messages?_format=for_api_partners")
        status_code, content = self._call_api(
            url, {"thread_id": thread_id, "message": message}, http_method="post"
        )
        if status_code not in [status.HTTP_200_OK, status.HTTP_201_CREATED]:
            raise Exception("Not 200")  # TODO should have an http error wrapper
        return json.loads(content)["message"]

    def get_thread(self, thread_id: int):
        url = urllib.parse.urljoin(self.netloc, f"threads/{thread_id}?_format=for_api_partners")
        status_code, content = self._call_api(url, None, http_method="get")
        return content

    def get_threads(self, order_asc=True):
        url = urllib.parse.urljoin(
            self.netloc,
            "threads/?{query_params}".format(
                query_params=urllib.parse.urlencode(
                    {
                        "_format": "for_api_partners",
                        "selected_inbox_type": "host",  # TODO Not always required
                        "_limit": 50,
                        "_offset": 0,  # TODO Fetch all reservations
                        "_order": "created_at asc" if order_asc else "created_at desc",
                        "role": "all",
                    }
                )
            ),
        )
        status_code, content = self._call_api(url, None, http_method="get")
        return content

    def push_review_status(self, listing_id: str):
        data = dict(
            id=listing_id,
            requested_approval_status_category=StatusCategory.ready_for_review.pretty_name,
        )
        url = urllib.parse.urljoin(self.netloc, f"listings/{listing_id}")
        status_code, content = self._call_api(url, data, "put")
        result = dict()
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["listing"]
        return result

    def push_link_and_review_status(self, listing_id: str):
        data = dict(
            id=listing_id,
            synchronization_category=AirbnbSyncCategory.sync_all.pretty_name,
            requested_approval_status_category=StatusCategory.ready_for_review.pretty_name,
        )
        url = urllib.parse.urljoin(self.netloc, f"listings/{listing_id}")
        status_code, content = self._call_api(url, data, "put")
        result = dict()
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["listing"]
        return result

    def push_link(self, listing_id: str):
        data = dict(
            id=listing_id,
            synchronization_category=AirbnbSyncCategory.sync_all.pretty_name,
        )  # TODO
        url = urllib.parse.urljoin(self.netloc, f"listings/{listing_id}")
        status_code, content = self._call_api(url, data, "put")
        result = dict()
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["listing"]
        return result

    def push_unlink(self, listing_id: str):
        data = dict(synchronization_category=None)
        url = urllib.parse.urljoin(self.netloc, f"listings/{listing_id}")
        status_code, content = self._call_api(url, data, "put")
        result = dict()
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["listing"]
        return result

    def push_listings(self, listings: Iterable):
        with ThreadPool(cpu_count()) as pool:
            return pool.map(self.push_listing, listings)

    def delete_photo(self, photo_id: str):
        url = urllib.parse.urljoin(self.netloc, f"listing_photos/{photo_id}")
        status_code, content = self._call_api(url, {}, "delete")
        result = dict()
        if status_code == status.HTTP_204_NO_CONTENT:
            result = json.loads(content)
        return result

    def update_photo(self, photo):
        data = dict(caption=photo.pop("caption", ""), sort_order=photo.pop("sort_order", 0))
        url = urllib.parse.urljoin(self.netloc, f"listing_photos/{photo['id']}")
        status_code, content = self._call_api(url, data, "put")
        result = dict()
        if status_code in [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT]:
            result = json.loads(content)
        return result

    def delete_listing(self, listing_id: str):
        url = urllib.parse.urljoin(self.netloc, f"listings/{listing_id}")
        status_code, content = self._call_api(url, {}, "delete")
        result = dict()
        if status_code in [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT]:
            result = json.loads(content)
        return result

    def update_listing(self, listing: dict):
        assert "id" in listing, "id is required"
        listing_id = listing["id"]
        extras = listing.pop("extras", {})
        locale = listing.get("locale", DEFAULT_LOCALE)
        url = urllib.parse.urljoin(self.netloc, f"listings/{listing_id}")
        status_code, content = self._call_api(url, listing, "put")
        response_ok = status_code == status.HTTP_200_OK
        if response_ok:
            response_json = json.loads(content)["listing"]
            response_json.update(self._push_listing_extras(listing_id, locale, extras))
            return response_json
        return {"error": content}

    def push_listing_rooms(self, listing_id, listing_rooms: list):
        """
        Push rooms to Airbnb

        :param listing_rooms: dictionary listing_rooms
        """
        for room in listing_rooms:
            room["listing_id"] = listing_id

        url = urllib.parse.urljoin(self.netloc, f"listing_rooms")
        push_room = partial(self._call_api, url, http_method="post")
        with ThreadPool(2) as pool:
            responses = pool.map(push_room, listing_rooms)

        ok_responses = (status.HTTP_200_OK, status.HTTP_201_CREATED)
        return [
            json.loads(room)["listing_room"] if status_code in ok_responses else {}
            for status_code, room in responses
        ]

    def push_availability_rule(self, listing_id, availability_rules: dict):
        url = urllib.parse.urljoin(self.netloc, f"availability_rules/{listing_id}")
        status_code, content = self._call_api(url, availability_rules, "put")
        result = dict()
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["availability_rule"]
        return result

    def _push_listing_extras(self, listing_id: int, locale: str, extras: dict):
        listing = dict()
        extras_update_functions = {
            "photos": self.sync_photos,
            "pricing_settings": self.push_pricing_settings,
            "booking_settings": self.push_booking_settings,
            "listing_rooms": self.push_listing_rooms,
            "availability_rules": self.push_availability_rule,
            "calendar_operations": self.push_availability,
        }
        for name, f in extras_update_functions.items():
            extra = extras.get(name, None)
            if not extra:
                continue
            listing[name] = f(listing_id, extra)

        descriptions = "listing_descriptions"
        if descriptions in extras:
            listing[descriptions] = self.push_descriptions(
                listing_id, extras.get(descriptions), locale
            )

        return listing

    def push_listing_extras(self, extras: dict, listing_id):
        return self._push_listing_extras(listing_id, DEFAULT_LOCALE, extras)

    def push_listing(self, listing: dict):
        url = urllib.parse.urljoin(self.netloc, "listings")
        status_code, content = self._call_api(url, listing, "post")
        response_ok = status_code == status.HTTP_200_OK
        if response_ok:
            new_listing = json.loads(content)["listing"]
        else:
            new_listing = {"error": content}
        return new_listing

    def push_descriptions(self, listing_id, descriptions: dict, locale):
        """
        Push descriptions in multiple languages to Airbnb

        :param descriptions: dictionary descriptions where keys are languages short codes
                             and values are actual descriptions
        """
        url = urllib.parse.urljoin(self.netloc, f"listing_descriptions/{listing_id}/{locale}")
        status_code, content = self._call_api(url, descriptions, "put")
        result = dict()
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["listing_description"]
        return result

    def get_photos(self, listing_id: str) -> list:
        url = urllib.parse.urljoin(self.netloc, f"listing_photos/?listing_id={listing_id}")
        status_code, content = self._call_api(url, {}, "get")
        result = list()
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["listing_photos"]
        return result

    def delete_photos(self, listing_id):
        photos = [photo["id"] for photo in self.get_photos(listing_id)]
        with ThreadPool(2) as pool:
            return pool.map(self.delete_photo, photos)

    def sync_photos(self, listing_id, photos):
        self.delete_photos(listing_id)
        return self.push_photos(listing_id, photos)

    def push_photos(self, listing_id, photos):
        for photo in photos:
            photo["listing_id"] = listing_id
        url = urllib.parse.urljoin(self.netloc, "listing_photos")
        push_photo = partial(self._call_api, url, http_method="post")
        with ThreadPool(2) as pool:
            responses = pool.map(push_photo, photos)

        ok_responses = (status.HTTP_200_OK, status.HTTP_201_CREATED)
        return [
            json.loads(photo)["listing_photo"] if status_code in ok_responses else {}
            for status_code, photo in responses
        ]

    def push_booking_settings(self, listing_id, booking_settings):
        url = urllib.parse.urljoin(self.netloc, f"booking_settings/{listing_id}")
        status_code, content = self._call_api(url, booking_settings, "put")
        result = dict()
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["booking_setting"]
        return result

    def push_pricing_settings(self, listing_id, pricing_settings):
        listing_currency = pricing_settings.pop("listing_currency", None)
        pricing_response = self.push_pricing(listing_id, pricing_settings)
        if listing_currency:
            currency_response = self.push_listing_currency(listing_id, listing_currency)
            pricing_response.update(currency_response)
        return pricing_response

    def _perform_push_pricing_settings(self, listing_id, pricing_settings):
        url = urllib.parse.urljoin(self.netloc, f"pricing_settings/{listing_id}")
        status_code, content = self._call_api(url, pricing_settings, "put")
        result = dict()
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["pricing_setting"]
        return result

    def push_pricing(self, listing_id, pricing_settings):
        return self._perform_push_pricing_settings(listing_id, pricing_settings)

    def push_listing_currency(self, listing_id, currency):
        return self._perform_push_pricing_settings(listing_id, {"listing_currency": currency})

    def push_availability(self, listing_id, availability: dict) -> dict:
        """Sets occupancy for 2 years in the future"""
        status_code, content = self._call_api(
            urllib.parse.urljoin(self.netloc, "calendar_operations?_allow_dates_overlap=true"),
            {"listing_id": listing_id, "operations": availability},
            "post",
        )
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["calendar_operation"]
        else:
            result = {}
        return result

    def get_reservation_by_confirmation_code(self, confirmation_code) -> dict:
        url = urllib.parse.urljoin(self.netloc, f"reservations/{confirmation_code}")
        status_code, content = self._call_api(url, {}, "get")
        result = dict()
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["reservation"]
        return result

    def get_reservations(self, listing_id) -> list:
        url = urllib.parse.urljoin(self.netloc, "reservations")
        params = urllib.parse.urlencode(
            {"listing_id": listing_id, "all_status": False, "_limit": 50, "_offset": 0}
        )
        status_code, content = self._call_api(f"{url}?{params}", {}, "get")
        result = list()
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["reservations"]
        return result

    def push_accept_reservation_request_by_confirmation_code(self, confirmation_code) -> dict:
        data = {"attempt_action": "accept"}
        url = urllib.parse.urljoin(self.netloc, f"reservations/{confirmation_code}")
        status_code, content = self._call_api(url, data, "put")
        result = dict()
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["reservation"]
        return result

    def push_deny_reservation_request_by_confirmation_code(self, confirmation_code) -> dict:
        data = {"attempt_action": "deny"}
        url = urllib.parse.urljoin(self.netloc, f"reservations/{confirmation_code}")
        status_code, content = self._call_api(url, data, "put")
        result = dict()
        if status_code == status.HTTP_200_OK:
            result = json.loads(content)["reservation"]
        return result

    def set_listing_details(self, listing_id, data):
        url = urllib.parse.urljoin(self.netloc, f"listing/{listing_id}")
        status_code, content = self._call_api(url, data, "put")

    def _authenticate(self, data, headers, context=None):
        return None

    def _parse_data(self, data: dict) -> str:
        return json.dumps({k: v for k, v in data.items()})

    @classmethod
    def to_airbnb(cls, listing) -> dict:
        from rental_integrations.airbnb.serializers import AirbnbListingSerializer

        serializer = AirbnbListingSerializer(listing)
        # serializer.is_valid(raise_exception=True)
        return serializer.data

        def airbnb_listing_attr(name):
            from rental_integrations.airbnb.models import AirbnbSync

            with suppress(AirbnbSync.DoesNotExist):
                airbnb_channel = AirbnbSync.objects.get(prop=listing)
                return getattr(airbnb_channel, name)

        old = timezone.make_aware(datetime(2000, 1, 1))
        to_update = timezone.now() - timedelta(hours=2)

        prop_type = mappings.cozmo_property_type[listing.property_type]
        booking_settings = getattr(listing, "booking_settings", None) or BookingSettings(
            check_in_out=CheckInOut(), date_updated=old
        )
        pricing_settings = getattr(listing, "pricing_settings", None) or PricingSettings(
            currency="USD", date_updated=old
        )
        desc = getattr(listing, "descriptions", None) or ListingDescriptions(date_updated=old)
        loc = listing.location

        airbnb_data = {
            "requested_approval_status_category": StatusCategory.new.pretty_name,
            "id": airbnb_listing_attr("external_id"),
            "name": listing.name,
            "property_type_group": mappings.type_to_group[prop_type],
            "property_type_category": prop_type,
            "room_type_category": mappings.cozmo_rental_type.get(listing.rental_type),
            "bedrooms": int(listing.bedrooms),
            "bathrooms": float(listing.bathrooms),
            "permit_or_tax_id": listing.license_number,
            "apt": getattr(loc, "apartment", ""),
            "street": getattr(loc, "address", ""),
            "city": getattr(loc, "city", ""),
            "state": getattr(loc, "state", ""),
            "zipcode": getattr(loc, "postal_code", ""),
            "country_code": getattr(loc, "country_code", ""),
            "lat": ("{:.6f}".format(loc.latitude) if getattr(loc, "latitude", None) else ""),
            "lng": ("{:.6f}".format(loc.longitude) if getattr(loc, "longitude", None) else ""),
            "user_defined_location": bool(loc and loc.latitude and loc.longitude),
            "directions": str(listing.arrival_instruction or ""),
            "person_capacity": listing.max_guests or 1,
            "listing_currency": pricing_settings.currency or "USD",
            "listing_price": int(pricing_settings.nightly or 0),
            "synchronization_category": AirbnbSyncCategory(
                airbnb_listing_attr("scope") or 1
            ).pretty_name,
            #  "bathroom_shared": None,  # TODO special circumstances
            #  "bathroom_shared_with_category": None,  # TODO special circumstances
            #  "common_spaces_shared": None,  # TODO special circumstances
            #  "common_spaces_shared_with_category": None,  # TODO special circumstances
            #  "total_inventory_count": None,  # TODO special circumstances
            "property_external_id": str(listing.id),  # TODO correct mapping
            "listing_rooms": [
                {
                    "room_number": 1,
                    "listing_room": {
                        "beds": [
                            {"type": x.room_type, "quantitiy": 1} for x in listing.room_set.all()
                        ],
                        "room_amenities": (
                            {"quantity": 1, "type": "en_suite_bathroom"}
                            if listing.bathrooms >= 1
                            else None
                        ),
                    },
                }
            ],
            "amenity_categories": [
                airbnb_amenity.value
                for airbnb_amenity in Amenity
                if getattr(listing.basic_amenities, airbnb_amenity.name, False)
            ],
            "extras": {},
        }

        if desc.date_updated > to_update:
            airbnb_data["extras"]["listing_description"] = {
                "en": {
                    "name": desc.name or listing.name,
                    "summary": desc.summary or desc.headline,
                    "space": f"Apartment is {desc.space} sq ft" if desc.space else "",
                    "access": desc.access,
                    "interaction": desc.interaction,
                    "transit": desc.transit,
                    "notes": desc.notes,
                    "neighborhood_overview": desc.neighborhood,
                    "house_rules": desc.house_manual,
                }
            }

        if booking_settings.date_updated > to_update:
            airbnb_data["extras"]["booking_settings"] = {
                "instant_booking_allowed_category": (
                    "everyone" if booking_settings.instant_booking_allowed else None
                ),
                "cancellation_policy_category": mappings.cozmo_cancellation_policy[
                    booking_settings.cancellation_policy
                ],
                "check_in_time_start": (
                    choices.CheckInOutTime.flexible
                    # booking_settings.check_in_out.check_in_from[:2] or "FLEXIBLE"
                ),
                "check_in_time_end": "FLEXIBLE",
                "check_out_time": None,
                "instant_book_welcome_message": None,
                "listing_expectations_for_guests": [],
                "guest_controls": {
                    "allows_children_as_host": False,
                    "allows_infants_as_host": False,
                    "allows_smoking_as_host": False,
                    "allows_pets_as_host": False,
                    "allows_events_as_host": False,
                },
            }

        availability = cls.to_airbnb_availability(listing)  # How to save requests?
        if availability:
            airbnb_data["extras"]["calendar_operations"] = availability

        if pricing_settings.date_updated > to_update:
            airbnb_data["extras"]["pricing_settings"] = {
                "default_daily_price": int(pricing_settings.nightly or 0),
                "cleaning_fee": int(pricing_settings.cleaning_fee or 0),
                "guests_included": int(pricing_settings.included_guests or 0),
                "security_deposit": int(pricing_settings.security_deposit or 0),
                "listing_currency": pricing_settings.currency,
                "price_per_extra_person": int(pricing_settings.extra_person_fee or 0),
                "weekend_price": int(pricing_settings.weekend or 0),
            }

        photos = [
            {
                "content_type": mimetypes.guess_type(img.url.name)[0],
                "filename": img.url.name,
                "image": b64encode(img.url.file.read()).decode(),
                "caption": img.caption,
                "sort_order": img.order,
                "listing_id": airbnb_listing_attr("external_id"),
            }
            for img in listing.image_set.self_hosted().filter(date_updated__gt=to_update)
            if img.url.file.size > 0
        ]
        if photos:
            airbnb_data["extras"]["photos"] = photos

        return airbnb_data

    @classmethod
    def to_airbnb_availability(cls, listing: "listings.models.Property") -> dict:
        to_update = timezone.now() - timedelta(hours=2)
        if (
            not listing.reservation_set.filter(date_updated__gt=to_update).exists()
            and not listing.blocking_set.filter(date_updated__gt=to_update).exists()
        ):
            return []

        def prepare_qs(qs):
            today = timezone.now().today()
            max_date = today + timedelta(days=365 * 2)

            return (
                qs.filter(end_date__gte=today, end_date__lte=max_date)
                .annotate(start=Greatest("start_date", today), end=Least("end_date", max_date))
                .values("start", "end")
            )

        def parse_dates(ev) -> str:
            if (ev["end"] - ev["start"]).days > 1:
                dates = "{}:{}".format(
                    ev["start"].isoformat(), (ev["end"] - timedelta(days=1)).isoformat()
                )
            else:
                dates = ev["start"].isoformat()
            return dates

        data = list()
        reservations_dates = [parse_dates(ev) for ev in prepare_qs(listing.reservation_set)]
        if reservations_dates:
            data.append(
                {
                    "dates": reservations_dates,
                    "availability": "unavailable",
                    "notes": "Cozmo reservations",
                }
            )
        blockings_dates = [
            parse_dates(ev)
            for ev in prepare_qs(
                listing.blocking_set.annotate(
                    start_date=Lower("time_frame"), end_date=Upper("time_frame")
                )
            )
        ]
        if blockings_dates:
            data.append(
                {
                    "dates": blockings_dates,
                    "availability": "unavailable",
                    "notes": "Cozmo blockings",
                }
            )

        return data

    def to_cozmo_reservation(self, reservation: dict) -> dict:
        return to_cozmo_reservation(reservation)

    def to_cozmo(self, listing: dict) -> dict:
        descriptions = listing.get("descriptions", defaultdict(str))
        booking_settings = listing.get("booking_settings", {})
        availability_rules = listing.get("availability_rules", {})
        pricing_settings = listing.get("pricing_settings", {})
        images = listing.get("photos")
        rooms = listing.get("listing_rooms")
        return {
            "name": listing["name"],
            "rental_type": mappings.airbnb_rental_type.get(listing["room_type_category"]),
            "property_type": mappings.airbnb_property_type.get(
                listing["property_type_category"]
            ).pretty_name,
            "bedrooms": listing["bedrooms"],
            "bathrooms": listing["bathrooms"],
            "license_number": listing["permit_or_tax_id"] or "",
            "max_guests": listing["person_capacity"],
            "pricing_settings": {
                "nightly": pricing_settings["default_daily_price"],
                "cleaning_fee": pricing_settings["cleaning_fee"] or 0.0,
                "included_guests": pricing_settings["guests_included"],
                "security_deposit": pricing_settings["security_deposit"] or 0.0,
                "currency": pricing_settings["listing_currency"],
                "extra_person_fee": pricing_settings["price_per_extra_person"] or 0.0,
                "weekend": pricing_settings["weekend_price"] or 0.0,
            },
            "airbnb_listing": {  # TODO
                "property_type_group": listing["property_type_group"],
                "instant_booking_category": booking_settings["instant_booking_allowed_category"],
            },
            "booking_settings": {
                "instant_booking_allowed": (
                    booking_settings["instant_booking_allowed_category"] != "off"
                ),
                "cancellation_policy": mappings.airbnb_cancellation_policy.get(
                    CancellationPolicy(booking_settings.get("cancellation_policy_category"))
                ),
                "check_in_out": _check_in_out(
                    booking_settings.get("check_in_time_start"),
                    booking_settings.get("check_in_time_end"),
                    booking_settings.get("check_out_time"),
                ),
            },
            "location": {
                "city": listing["city"],
                "state": listing["state"] or "",
                "address": listing["street"],
                "postal_code": listing["zipcode"],
                "apartment": listing["apt"] or "",
                "country_code": listing["country_code"],
                "country": listing["country_code"],
                "latitude": listing["lat"],
                "longitude": listing["lng"],
            },
            "descriptions": {
                "summary": descriptions["summary"] or "",
                "space": descriptions["space"] or "",
                "access": descriptions["access"] or "",
                "house": descriptions["house_rules"] or "",
                "notes": descriptions["notes"] or "",
                "neighborhood": descriptions["neighborhood_overview"] or "",
                "transit": descriptions["transit"] or "",
                "interaction": descriptions["interaction"] or "",
            },
            "locale": descriptions["locale"],
            "basic_amenities": self.to_cozmo_from_amenities(listing["amenity_categories"]),
            "images": self.to_cozmo_from_images(images),
            "rooms": self.to_cozmo_from_rooms(rooms),
            "availability_settings": self.to_cozmo_from_availability_rules(availability_rules),
            "suitability": self.to_cozmo_from_guest_controls(booking_settings),
            "fees": self.to_cozmo_from_standard_fees(pricing_settings),
        }

    @classmethod
    def to_cozmo_from_standard_fees(self, pricing_settings):
        fees = list()
        standard_fees = pricing_settings.get("standard_fees")
        for fee in standard_fees:
            amount_type = fee["amount_type"]
            is_percent_type = amount_type == AmountType.percent.value
            data = {
                "value": float(fee["amount"]) if is_percent_type else int(fee["amount"] / 1e6),
                "type": mappings.airbnb_to_cozmo_fee_types.get_by_name_to_pretty(fee["fee_type"]),
                "calculation_method": CalculationMethod.Per_Stay.pretty_name,
                "is_percentage": is_percent_type,
            }
            fees.append(data)
        return fees

    @classmethod
    def to_cozmo_from_guest_controls(self, booking_settings):
        guest_controls = booking_settings.get("guest_controls", {})
        yes = Suitability.SuitabilityProvided.Yes.pretty_name
        no = Suitability.SuitabilityProvided.No.pretty_name
        data = dict(
            elderly=no,
            pets=yes if guest_controls["allows_pets_as_host"] else no,
            kids=yes if guest_controls["allows_children_as_host"] else no,
            large_groups=no,
            events=yes if guest_controls["allows_events_as_host"] else no,
            smoking=yes if guest_controls["allows_smoking_as_host"] else no,
            handicap=no,
            infants=yes if guest_controls["allows_infants_as_host"] else no,
            children_not_allowed_details=guest_controls["children_not_allowed_details"],
        )
        return data

    def to_cozmo_from_availability_rules(self, rules):
        data = dict(
            min_stay=rules["default_min_nights"],
            max_stay=rules["default_max_nights"],
            preparation=rules["turnover_days"]["days"],
            advance_notice=rules["booking_lead_time"]["hours"],
            check_in_days=[
                WeekDays(day["day_of_week"]).value for day in rules["day_of_week_check_in"]
            ],
            check_out_days=[
                WeekDays(day["day_of_week"]).value for day in rules["day_of_week_check_out"]
            ],
            days_min_nights={
                x["day_of_week"]: x["min_nights"] for x in rules["day_of_week_min_nights"]
            },
            # min_age=,
            # window=,
        )
        return data

    @classmethod
    def to_cozmo_from_rooms(self, rooms):
        airbnb_rooms = list()
        for room in rooms:
            airbnb_beds = list()
            for bed in room["beds"]:
                airbnb_beds += [
                    mappings.airbnb_beds.get(choices.BedType(bed["type"])).pretty_name
                ] * bed["quantity"]
            room_number = room["room_number"]
            is_common_room = room_number == 0
            room_type = Room.Types.Common if is_common_room else Room.Types.Bedroom
            room_data = dict(description="", type=room_type.pretty_name, beds=airbnb_beds)
            for amenity in room["room_amenities"]:
                if amenity["type"] == "en_suite_bathroom":
                    room_data["bathrooms"] = amenity["quantity"]

            airbnb_rooms.append(room_data)
        return airbnb_rooms

    def to_cozmo_from_images(self, photos):
        images = [
            dict(
                external_id=photo.get("id"),
                caption=photo.get("caption", ""),
                url=photo.get("large_url"),
                order=photo.get("sort_order"),
            )
            for photo in photos
        ]
        return images

    def to_cozmo_from_amenities(self, amenities):
        cozmo_amenities = dict()
        for amenity in amenities:
            try:
                cozmo_amenities[Amenity(amenity).name] = True
            except Exception as e:
                logger.error(f"Amenity not recognized {amenity} - {e}")
        return cozmo_amenities

    def to_cozmo_from_photos(self, photos):
        return [
            dict(url=photo["large_url"], order=photo["sort_order"], caption=photo["caption"])
            for photo in photos
        ]

"""Legacy module."""

import base64
import binascii
import hashlib
import logging
import os
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta
from itertools import chain

from rest_framework import status

from cozmo_common.functions import deep_get
from listings.models import Property
from rental_integrations.exceptions import ServiceException
from rental_integrations.service import BaseService
from rental_integrations.tools import strip_falsy

BASE_URL = "https://dispatch.homeaway.com"


def _cleaning_fee(listing_fees):
    try:
        value = next(
            fee.get("maxAmount")
            for fee in (listing_fees or [])
            if fee.get("type", "").upper() == "CLEANING_FEE"
        )
    except StopIteration:
        value = 0
    return value


def _check_in_out(check_in, check_out):
    if check_in is not None and check_out is not None:
        return {
            "check_in_to": str(check_in)[:2] + ":00",
            "check_out_until": str(check_out)[:2] + ":00",
        }
    else:
        return None


def to_cozmo_property(listing) -> dict:
    prop = dict(
        id=listing.get("listingId"),
        name=not listing.get("propertyName")
        and listing.get("headline")
        or listing.get("propertyName"),
        status=Property.Statuses.Active.name,
        description=listing.get("description", ""),
        space=listing.get("area", ""),
        time_zone="",
        license_number="",
        property_type=listing.get("propertyType", "Other"),
        rental_type="Other",  # FIXME Parse airbnb data and set accordingly
        max_guests=listing.get("sleeps", 0),
        #  owner='',  # TODO
        location=dict(
            country=listing.get("address", {}).get("country", ""),
            region=listing.get("address", {}).get("stateProvince", ""),
            city=listing.get("address", {}).get("city", ""),
        ),
        arrival_instruction=dict(description="", landlord="", email="", phone=""),
        coordinates=dict(
            longitude=listing.get("geoCode", {}).get("longitude"),
            latitude=listing.get("geoCode", {}).get("latitude"),
        ),
        amenities=[
            {"name": n.replace("_", " ").lower().capitalize()}
            for n in listing.get("featuredAmenities", [])
        ],
        images=[
            dict(caption=ph.get("caption") or "", url=ph.get("uri"))
            for ph in listing.get("images", [])
        ],
        pricing_settings={
            "nightly": listing.get("averagePrice", {}).get("value", 0),
            "security_deposit": listing.get("refundableDamageDeposit", 0),
            "cleaning_fee": _cleaning_fee(deep_get(listing, "rateSummary", "flatFees")),
            "included_guests": listing.get("sleeps", 0),
        },
        rooms=list(
            chain(
                (
                    {"description": "Bedroom", "type": "Bedroom"}
                    for i in range(int(listing.get("bedrooms", 0)))
                ),
                (
                    {"description": "Bathroom", "type": "Bathroom"}
                    for i in range(int(listing.get("bathrooms", {}).get("full", 0)))
                ),
            )
        ),
    )
    return strip_falsy(prop)


class HomeAwayService(BaseService):
    logger = logging.getLogger(__name__)

    def __init__(self, *args, **kwargs):
        self._user_id = kwargs.pop("user_id", None)
        self._device_id = kwargs.pop("device_id", None)
        self._matrix_id = kwargs.pop("matrix_id", None)
        super(HomeAwayService, self).__init__(*args, **kwargs)

    def get_headers(self, headers=dict()):
        default_headers = {
            "X-HomeAway-Restfully": "true",
            "X-Bizops-Enabled": "true",
            "X-HomeAway-DisplayLocale": "en_US",
            "X-HomeAway-Client": "owner",
            "X-HomeAway-AndroidVersion": "2017.4.2390",
            "User-Agent": "okhttp/2.2.0",
            "X-HomeAway-ThreatMetrix-ID": "73ed43c4-11ec-46f4-aca3-3feb5df9e405",
        }
        if getattr(self, "_access_token", None):
            default_headers["X-HOMEAWAY-THIN-UI-HA-SESSION"] = self._access_token
        if getattr(self, "_device_id", None):
            default_headers["X-HomeAway-DeviceId"] = self._device_id
        if getattr(self, "_matrix_id", None):
            default_headers["X-HomeAway-ThreatMetrix-ID"] = self._matrix_id

        default_headers.update(headers)
        return default_headers

    def get_basic_auth_header(self, username, password):
        auth_64_encoded = base64.b64encode("{}:{}".format(username, password).encode())
        return "Basic {}".format(auth_64_encoded.decode("utf-8"))

    def get_params(self, params=dict()):
        return params

    def format_path(self, path, path_kwargs):
        url = "{}/{}".format(BASE_URL, path.format(path_kwargs))
        return url

    def need_to_auth(self, resp):
        if resp.url.startswith(self.format_path("modash/v3/accounts/details", {})):
            return False

        if not self._access_token:
            return True

        if resp.status_code == status.HTTP_401_UNAUTHORIZED:
            return True
        return False

    def authenticate(self, username, password):
        path = "modash/v3/accounts/details"
        auth_header = self.get_basic_auth_header(username, password)
        self._device_id = binascii.b2a_hex(os.urandom(8)).decode("utf8")
        self._matrix_id = str(uuid.uuid4())

        headers = {"Authorization": auth_header}
        if self._access_token:
            self._access_token = None
        request_headers = self.get_headers(headers)

        resp = self._get(path, headers=request_headers)
        data = resp.json()
        to_return = {}
        if resp.status_code == status.HTTP_200_OK:
            self._user_id = data["userID"]
            self._access_token = resp.cookies["HA_SESSION"]

            to_return = {"access_token": self._access_token, "user_id": self._user_id}
        elif resp.status_code == status.HTTP_412_PRECONDITION_FAILED:
            if data["status"] == "CHALLENGE_PHONE":
                to_return = self.handle_status_412(data)
        elif resp.status_code == status.HTTP_403_FORBIDDEN:
            return dict(data=resp.json(), success=False, status=resp.status_code)
        else:
            dict(success=False, data=None, status=resp.status_code)

        if callable(self._auth_callback):
            self._auth_callback(service=self)
        return dict(data=to_return, success=True, status=resp.status_code)

    def handle_status_412(self, data):
        self.logger.debug("Handle 412 status code")
        return dict(
            authenticationSession=data["authenticationSession"], phoneNumbers=data["phoneNumbers"]
        )

    def get_session_info(self):
        return dict(
            access_token=self._access_token,
            user_id=self._user_id,
            device_id=self._device_id,
            matrix_id=self._matrix_id,
        )

    def get_user_id(self):
        if self._user_id:
            return self._user_id

        path = "modash/v3/accounts/details"
        request_headers = self.get_headers()
        resp = self._get(path, headers=request_headers)
        data = resp.json()

        if resp.status_code == status.HTTP_200_OK:
            self._user_id = data["userID"]

        return self._user_id

    def get_threads(self, offset=1, limit=20):
        path = "modash/v3/inbox"
        params = {"count": limit, "startPage": offset}
        resp = self._get(path, params=params)
        data = resp.json()

        DATE = "%Y-%m-%d"
        if resp.ok:
            threads_json = data["conversations"]
            threads = list()
            for t in threads_json:
                thread = dict()
                thread["id"] = t["conversationID"]
                thread["lastReceived"] = t["lastMessage"]
                thread["message"] = t["messageText"] if t["messageText"] else t["currentState"]
                thread["unread"] = t["unreadMessages"]
                thread["status"] = t["currentState"]

                user_json = t["correspondents"][0]
                other_user = dict(
                    name=user_json["name"],
                    id=user_json["uuid"],
                    avatarUrl=user_json["avatar"],
                    email=user_json["email"],
                    phone=user_json["phone"],
                )
                thread["otherUser"] = other_user
                check_out_json = t["checkOutDay"]
                check_in_json = t["checkInDay"]
                if check_out_json and check_in_json:
                    check_out_date = datetime.strptime(check_out_json, DATE)
                    check_in_date = datetime.strptime(check_in_json, DATE)
                    delta = check_out_date - check_in_date
                    thread["nights"] = delta.days
                    thread["checkIn"] = t["checkInDay"]
                    thread["checkOut"] = t["checkOutDay"]
                thread["guests"] = t["numAdults"] + t["numChildren"]
                listing = t["property"]
                if listing:
                    thread["listing"] = dict(
                        name=listing["propertyName"],
                        thumbnailUrl=listing["thumbnail"],
                        id=listing["listingRef"],
                    )
                threads.append(thread)
            response_data = dict(threads=threads)
            return response_data
        raise ServiceException(data.get("messages", ""), **data)

    def get_thread_posts(self, thread_id):
        path = (
            "modash/v3/inbox/conversation/{}?"
            "hydrated=true&haxOff=true&supplierHomeComponents=PAYMENT_DETAILS&"
            "supplierHomeComponents=QUOTE&supplierHomeComponents="
            "CONVERSATION&supplierHomeComponents=MESSAGES".format(thread_id)
        )
        resp = self._get(path)
        data = resp.json()
        if resp.ok:
            from pprint import pprint

            pprint(data)
            conversation_json = data["conversation"]
            thread_json = conversation_json["messages"]
            thread_id = conversation_json["conversationID"]
            status = conversation_json["currentState"]

            guest_json = conversation_json["travelers"][0]
            guest = dict(
                name=guest_json["name"],
                id=guest_json["uuid"],
                pictureUrl=guest_json["avatar"],
                avatarUrl=guest_json["avatar"],
                email=guest_json["email"],
                phone=guest_json["phone"],
            )
            host_json = conversation_json["owners"][0]
            host = dict(
                name=host_json["name"],
                id=host_json["uuid"],
                pictureUrl=host_json["avatar"],
                avatarUrl=host_json["avatar"],
                email=host_json["email"],
                phone=host_json["phone"],
            )
            users = dict(host=host, guest=guest)

            messages = list()
            for m in thread_json:
                message = dict()
                message["dateCreated"] = m["messageDate"]
                message["id"] = m["messageID"]
                message["message"] = m["messageText"]
                sender_json = m["from"]
                if sender_json:
                    message["user_id"] = sender_json["uuid"]
                messages.append(message)

            property_json = conversation_json["property"]

            listing = dict(
                id=property_json["listingRef"],
                pictureUrl=property_json["thumbnail"],
                name=property_json["propertyName"],
                # bedrooms=listing_json['bedrooms'],
                # bathrooms=listing_json['bathrooms'],
                # beds=listing_json['beds'],
                # address=listing_json['address'],
                # cancellationPolicy=listing_json['cancellation_policy'],
                # propertyType=listing_json['property_type'],
                # roomType=listing_json['room_type'],
                # reviewCount=listing_json['reviews_count'],
                # inquiryPriceNative=listing_json['inquiry_price_native']
            )

            reservation_info = dict(
                check_in_date=conversation_json["checkInDay"],
                check_out_date=conversation_json["checkOutDay"],
                status=status,
                listing=listing,
            )

            return dict(reservation=reservation_info, messages=messages, users=users, id=thread_id)
        raise ServiceException(data.get("messages", ""), **data)

    def post_message(self, thread_id, message):
        path = "modash/v3/inbox/conversation/{}".format(thread_id)
        payload = {"payload": message, "type": "replied"}
        resp = self._post(path, json=payload)
        data = resp.json()
        if resp.ok:
            return data["message"]["id"]

        raise ServiceException(data.get("error_message", ""), **data)

    def get_public_listing(self, listing_ref):
        system_id, property_id, unit_id = listing_ref.split(".")

        path = "bizops/listingSearch/details"
        params = {
            "supportsIpmOlb": "true",
            "_view": "mobileDetailsV2",
            "systemId": system_id,
            "propertyId": property_id,
            "unitId": unit_id,
            "currency": "USD",
            "olbEnabledForLocale": "true",
            "sessionId": "ce81f15e-9684-4fde-a222-07d7ad3d19a1",
            "visitorId": "5c92d34478c29c38",
            "partnerId": "mobile_30",
        }
        resp = self._get(path, params=params)
        data = resp.json()
        if resp.ok:
            return data
        raise ServiceException(data.get("error_message", ""), **data)

    def get_listing_info(self, listing_id):
        return self.get_public_listing(listing_id)

    def get_host_listing(self, listing_ref):
        path = "modash/v4/listingManagement/listings/{}".format(listing_ref)
        resp = self._get(path)
        data = resp.json()
        if resp.ok:
            return dict(
                id=data["listingRef"],
                name=data["title"],
                thumbnail=data["listingPhotos"]["publishedPhotos"][0]["fullSizeImage"]["url"],
                picture_url=data["listingPhotos"]["publishedPhotos"][0]["fullSizeImage"]["url"],
            )
        raise ServiceException(data.get("error_message", ""), **data)

    def get_host_listings(self, offset=0, limit=50, has_availability=False):
        """
        Get all listings for given host
        """
        path = "modash/v4/ownerinfo"
        resp = self._get(path)
        data = resp.json()

        if resp.ok:
            property_info = data["propertyInfo"]

            listing_refs = [each["listing"]["listingRef"] for each in property_info]
            listings = [self.get_public_listing(ref) for ref in listing_refs]
            return [to_cozmo_property(each) for each in listings], listings
        raise ServiceException(data.get("error_message", ""), **data)

    def calendar_days(self, listings, start_date, end_date):
        """
        Get the calendar days from given listings between start_date and
        end_date. Returns a ordered dict with busy days, like:

        {
          UID: [
            {
              "day": datetime.date(2016, 4, 7),
              "start_date": datetime.date(2016, 4, 1)
              "end_date": datetime.date(2016, 4, 10)
              "guest": {
                "email": "felipe-blahblaheds3wd2sd@service.com",
                "id": "felipe-blahblaheds3wd2sd@service.com",
                "name": "Felipe Prenholato"
              }
              "description" "some usefull text",
              "confirmation_code": "T4YSF9"

            },
            ...
          ],
          ...
        }

        The dict is ordered by UID, and then by date.
        The UID is created by Service.generate_uid()
        """
        path = "v2/calendar_days"
        _requests = []
        for _id in listings:
            _requests.append(
                {
                    "method": "GET",
                    "path": path,
                    "query": {
                        "listing_id": _id,
                        "start_date": datetime.strptime(start_date, "%Y-%m-%d"),
                        "end_date": datetime.strptime(end_date, "%Y-%m-%d"),
                        "_format": "host_calendar_detailed",
                    },
                }
            )
        data = OrderedDict()
        operations = self._batch(*_requests)
        for resp in operations["operations"]:
            days = resp["response"]["calendar_days"]
            _id = resp["query"]["listing_id"]
            reservations = {}
            for day in days:
                if day["available"]:
                    continue
                info = {
                    "day": datetime.strptime(day["date"], "%Y-%m-%d").date(),
                    "start_date": datetime.strptime(
                        day["reservation"]["start_date"], "%Y-%m-%d"
                    ).date(),
                    "guest": {
                        "email": "",
                        "id": day["reservation"]["guest"]["id"],
                        "name": day["reservation"]["guest"]["full_name"],
                    },
                    "description": "",
                    "confirmation_code": day["reservation"]["confirmation_code"],
                    "uid": self.generate_uid(_id, day),
                    "listing_id": _id,
                }
                # calculate start and end_date
                if day["group_id"] not in reservations:
                    nights = day["reservation"]["nights"]
                    reservations[day["group_id"]] = {
                        "start_date": info["start_date"],
                        "end_date": info["start_date"] + timedelta(days=nights),
                    }
                info.update(reservations[day["group_id"]])
                if info["day"] not in data:
                    data[info["day"]] = OrderedDict()
                data[info["day"]][info[" uid"]] = info

        return data

    def generate_uid(self, listing_id, data):
        s = "{}-{}".format(listing_id, data["group_id"].split(":")[1])
        uid = "{}@airbnb.com".format(base64.urlsafe_b64encode(hashlib.md5(str(s)).hexdigest()))
        return uid

    def set_message_status(self, thread_id, unread):
        mark_read = "markRead"
        mark_unread = "markUnread"
        path = "modash/v4/conversations/{}".format(mark_unread if unread else mark_read)
        data = dict(conversationIds=[thread_id])
        resp = self._post(path, json=data)
        if resp.ok:
            return data

        raise ServiceException(data.get("error_message", ""), **data)

    def get_all_reservations_by_listing(self, listing_id, start_date="", end_date=""):
        path = "modash/v3/ownerinfo"

        resp = self._get(path)
        data = resp.json()
        if resp.ok:
            property_info = data["propertyInfo"]
            listing_filter = [x for x in property_info if x["listing"]["listingRef"] == listing_id]
            if not listing_filter:
                raise Exception("Listing with id {} not found".format(listing_id))
            reservation_raw = [
                x for x in listing_filter[0]["reservations"] if x["status"] == "RESERVE"
            ]
            reservations = list()
            date_format = "%Y-%m-%d"
            if not start_date and not end_date:
                start_date = datetime.now().strftime(date_format)
            start_date_time = datetime.strptime(start_date, date_format)

            for each in reservation_raw:
                reservation_date_time = datetime.strptime(each["checkInDay"], date_format)
                if not start_date or start_date_time <= reservation_date_time:
                    reservations.append(
                        dict(
                            search_key="uuid",
                            search_value=each["uuid"],
                            start_date=each["checkInDay"],
                            guest_first_name=each["firstName"],
                        )
                    )

            return reservations

        raise ServiceException(data.get("error_message", ""), **data)

    def get_reservation_details(self, *args, **kwargs):
        path = "modash/v3/inbox/conversation/findBy"

        uuid = kwargs.get("uuid")

        if not uuid:
            raise Exception("Missing parameters")

        params = dict(
            hydrated=True,
            haxOff=True,
            supplierHomeComponents="PAYMENT_DETAILS",
            type="RESERVATION",
            uuid=uuid,
        )

        resp = self._get(path, params=params)
        data = resp.json()
        if resp.ok:
            reservation = data["conversation"]["reservation"]
            reservation_id = reservation["reservationID"]
            start_date = reservation["checkInDay"]
            end_date = reservation["checkOutDay"]
            start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
            end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
            delta = end_datetime - start_datetime
            num_nights = delta.days
            num_guests = reservation["numAdults"] + reservation["numChildren"]
            status = "accepted"
            guest_user = data["conversation"]["travelers"][0]
            guest_name = guest_user["name"]
            guest_email = guest_user["email"]
            guest_proxy_email = ""
            guest_phone = guest_user["phone"]
            guest_picture_url = guest_user["avatar"]
            guest_thumbnail_url = guest_user["avatar"]
            thread_id = data["conversation"]["conversationID"]
            guest_extra_info = dict()

            payment_info = data["conversation"]["paymentInfo"]
            if payment_info:
                total_price = payment_info["totalPaymentAmount"]
                payout_amount = payment_info["ownerPaymentAmount"]
            else:
                total_price = None
                payout_amount = None

            quote = data["quoteTemplate"]

            breakdown_price = list()

            for each in quote["fees"]:
                p_type = each["type"]
                if p_type == "RENTAL_AMOUNT":
                    name = "Rental Fee"
                elif p_type == "FEE":
                    name = "Cleaning Fee"
                elif p_type == "TRAVELER_FEE":
                    name = "Service Fee"
                elif p_type == "REFUNDABLE_DAMAGE_DEPOSIT":
                    name = "Security Deposit"
                elif p_type == "BOOKING_COMMISSION":
                    name = "Booking Commission"
                else:
                    name = (
                        each["name"] if "name" in each else "{}: {}".format("Other", each["type"])
                    )
                breakdown_price.append(dict(name=name, amount=each["amountWithTax"]["amount"]))

            data = dict(
                reservation_id=reservation_id,
                start_date=start_date,
                end_date=end_date,
                num_nights=num_nights,
                num_guests=num_guests,
                status=status,
                guest_name=guest_name,
                guest_email=guest_email,
                guest_proxy_email=guest_proxy_email,
                guest_picture_url=guest_picture_url,
                guest_thumbnail_url=guest_thumbnail_url,
                guest_phone=guest_phone,
                guest_thread_id=thread_id,
                guest_extra_info=guest_extra_info,
                total_price=total_price,
                price_info=breakdown_price,
                payout_amount=payout_amount,
                source="homeaway",
                json=data,
            )
            return data

        raise ServiceException(data.get("error_message", ""), **data)

    def submit_challenge_request(self, data):
        """
        Submit voice challenge to request verification code
        """
        path = "modash/v3/2fa/sendCode"
        payload = dict(
            authenticationSession=data.get("authenticationSession"),
            locale="en_US",
            notificationType="SMS",
            phoneNumberId=data.get("phone_id"),
        )
        return self._post(path, json=payload, retry=False)

    def submit_challenge_verification(self, data):
        """
        Submit verification code for challenge
        """
        path = "modash/v3/2fa/verifyCode"
        payload = dict(
            authenticationSession=data.get("authenticationSession"),
            verificationCode=data.get("code"),
        )
        return self._post(path, json=payload, retry=False)

    def get_dashboard_alerts(self):
        # not implemented
        return list()

    def set_listing_prices_by_date_range(self, listing_id, price, start_date, end_date):
        """
        Overrides daily pricing for a given date range
        :param start_date:
        :param end_date:
        :return:
        """
        raise NotImplementedError()

    def set_listing_prices_by_day(self, listing_id, price, single_date):
        """
        Overrides daily pricing for a given day
        :param listing_id:
        :param price:
        :param single_date:
        :return:
        """
        raise NotImplementedError()

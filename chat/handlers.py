import logging
from abc import abstractmethod

from chat.choices import ChatSetting
from chat.responses import get_template
from chat.utils import get_distance_str
from listings.models import Suitability
from services.google import GoogleService
from services.yelp import YelpService

logger = logging.getLogger(__name__)

POSITIVE = "positive"
NEGATIVE = "negative"
NEUTRAL = "neutral"


class SimpleResponseHandler:
    """
    For responses that only contains one type
    i.e. hello, thank you
    """

    def __init__(self, intent, message, **kwargs):
        self.message = message
        self.intent = intent.split(".")[-1]

    def is_allowed(self):
        pass

    def get_template(self, template_type):
        return get_template(self.intent, template_type)

    def execute(self):
        return ""
        # settings = self.message.conversation.reservation.prop.organization.settings.chat_settings
        # settings_attr = getattr(settings, f"{self.intent}_enabled")
        # handler = responses.get(settings_attr)
        # if handler:
        #     message = responses.get(settings_attr, lambda x: "")()
        #     return message
        # return ""


class ResponseHandler(SimpleResponseHandler):
    """
    For custom responses0
    """

    def __init__(self, parameters=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parameters = parameters

    @property
    def prop(self):
        return self.message.conversation.reservation.prop

    def get_ask_always_response(self):
        return self.get_template(NEUTRAL)

    def get_auto_always_response(self):
        """
        Check to see if this is makes sense
        :return:
        """
        is_positive, data = self.get_data()
        template = self.get_template(POSITIVE if is_positive else NEGATIVE)
        return template.format(**data)

    def get_no_always_response(self):
        return self.get_template(NEGATIVE)

    def _is_positive_response(self):
        is_positive, _ = self.get_data()
        return is_positive

    def execute(self):
        """
        if disabled: no nothing
        if no, just respond the intent's negative rewsponse
        if ask, just respond with the intent's neutral response
        if enabled, just respond with intent's positive response + special data'
        :return:
        """
        settings = self.prop.organization.settings.chat_settings
        responses = {
            ChatSetting.ASK_ALWAYS.value: self.get_ask_always_response,
            ChatSetting.AUTO_ALWAYS.value: self.get_auto_always_response,
            ChatSetting.NO_ALWAYS.value: self.get_no_always_response,
        }
        settings_attr = getattr(settings, f"{self.intent.replace('-', '_')}_enabled")
        handler = responses.get(settings_attr)
        logger.debug(f"Got settings {settings_attr} for {self.intent}")
        if handler:
            message = responses.get(settings_attr, lambda x: "")()
            return message
        return ""

    @abstractmethod
    def get_data(self):
        pass


class AmenitiesHandler(ResponseHandler):
    def get_data(self):
        basic_amenities = self.prop.basic_amenities

        amenity_mapping = {
            "elevator": "elevator",
            "hangers": "hangers",
            "parking": "parking",
            "hair dryer": "hair_dryer",
            "heating": "heating",
            "dryer": "dryer",
            "air conditioning": "ac",
            "washer": "washer",
            "tv": "tv",
            "kitchen": "kitchen",
            "wifi": "wireless_internet",
            "pool": "pool",
            "pocket wifi": "pocket_wifi",
            "iron": "iron",
            "grill": "grill",
            "essentials": "essentials",
            "fireplace": "fireplace",
            "private entrance": "private_entrance",
            "shampoo": "shampoo",
            "linens": "linens",
            "extra pillows": "extra_pillows_blankets",
            "extra blankets": "extra_pillows_blankets",
            "laptop friendly workplace": "laptop_friendly_workplace",
        }
        # for p in self.parameters["amenities"]:
        #     if getattr(basic_amenities, p, False):
        #         return
        target = self.parameters["amenities"][0]
        is_positive = getattr(basic_amenities, amenity_mapping.get(target, target), False)
        return is_positive, {"amenity": target}


class EarlyBagDropoffHandler(ResponseHandler):
    def get_data(self):
        pass


class CancellationHandler(ResponseHandler):
    def get_data(self):
        pass


class DiscountHandler(ResponseHandler):
    def get_data(self):
        pass


class EarlyCheckInHandler(ResponseHandler):
    def get_data(self):
        pass


class LateCheckOutHandler(ResponseHandler):
    def get_data(self):
        pass


class PetsHandler(ResponseHandler):
    def get_data(self):
        suitability = self.prop.suitability

        pets_allowed = suitability.pets == Suitability.SuitabilityProvided.Yes.value
        return pets_allowed, {}


class RefundHandler(ResponseHandler):
    def get_data(self):
        pass


class WifiHandler(ResponseHandler):
    def get_data(self):
        amenities = self.prop.basic_amenities
        ssid = amenities.wifi_ssid
        password = amenities.wifi_password
        if amenities.wireless_internet and ssid and password:
            return True, {"ssid": ssid, "password": password}
        return False, {}


class RecommendationHandler(ResponseHandler):
    def get_data(self):
        service = YelpService()
        location = self.prop.location

        results = service.get_recommendations(
            latitude=location.latitude, longitude=location.longitude
        )
        items = [
            "For {term}, you could try {name} ({address}), it's about {distance} away.\n".format(
                name=results[r][0]["name"],
                distance=get_distance_str(results[r][0]["distance"]),
                category=results[r][0]["categories"][0],
                address=results[r][0]["address"],
                term=r,
            )
            for r in results.keys()
        ]
        return True, {"recommendations": "\n".join(items)}


class DistanceHandler(ResponseHandler):
    def get_data(self):
        service = GoogleService()
        address = list()
        if self.parameters["location"]:
            pass
        elif self.parameters["to"]:
            for p in self.parameters["to"]:
                address_dict_template = {
                    "street-address": "",
                    "city": "",
                    "subadmin-area": "",
                    "admin-area": "",
                    "zip-code": "",
                }
                address_template = (
                    "{street-address}|{city}|{subadmin-area}|{admin-area}|{zip-code}"
                )
                address_dict_template.update(p)
                address.extend(
                    [
                        x
                        for x in address_template.format(**address_dict_template).split("|")
                        if x != ""
                    ]
                )

            result = service.get_distance_by_address(
                origin=self.prop.full_address, destination=", ".join(address)
            )
            if result:
                return True, {"driving_time": result["driving_time"]}
        return False, dict()

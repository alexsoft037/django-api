import json
import logging
from collections import namedtuple
from enum import auto

from django.conf import settings
from nexmo import Client as NexmoClient
from twilio.base.exceptions import TwilioRestException
from twilio.request_validator import RequestValidator
from twilio.rest import Client as TwilioClient

from cozmo_common.enums import StrChoicesEnum
from notifications import utils

logger = logging.getLogger(__name__)


class ServiceError(Exception):
    """Generic exception that a Service may raise on failure."""


PhoneNumber = namedtuple(
    "PhoneNumber", ["country_code", "msisdn", "capabilities", "number_type", "rental_price"]
)


class Capabilities(StrChoicesEnum):
    SMS = auto()
    VOICE = auto()


class PhoneType(StrChoicesEnum):
    LANDLINE = auto()
    LANDLINE_TOLL_FREE = auto()
    MOBILE_LVN = auto()


class SMSService(object):
    def __init__(self, client=None):
        self.client = client

    def send(self, *, _from, text, to):
        """Send a text message to a given number.

        Args:
            text (str): message to be send.
            to (str): phone number capable of receiving text messages.

        Returns:
            str: id of a message.

        Raises:
            ServiceError: message could not be sent.
        """
        if not isinstance(to, str):
            raise ServiceError("Invalid recipient number: {}".format(to))

        response, sid = self.perform_send(
            _from=utils.to_e164(_from), to=utils.to_e164(to), text=text
        )
        logger.debug("Response: " + str(response))
        return sid

    def perform_send(self, _from, to, text):
        raise NotImplementedError()

    def get_numbers(self, **kwargs):
        raise NotImplementedError()

    def search_available_numbers(
        self, country_code: str, capabilities: list, phone_type: PhoneType, pattern: str, **kwargs
    ):
        """

        :param country_code: ISO-3166 format country code (i.e. "US")
        :param capabilities: Phone number capabilities
        :param pattern: Search pattern for phones
        :param kwargs:
        :return:
        """
        raise NotImplementedError()

    def purchase_number(self, country_code: str, msisdn: str, **kwargs):
        raise NotImplementedError()

    def cancel_number(self, country_code: str, msisdn: str, **kwargs):
        raise NotImplementedError()

    def update_number(self, country_code: str, msisdn: str, **kwargs):
        raise NotImplementedError()


class NexmoService(SMSService):
    def to_internal_phone_numbers(self, data):
        if data:
            return [self.to_internal_phone_number(d) for d in data["numbers"]]
        return list()

    def to_internal_phone_number(self, data):
        return PhoneNumber(
            country_code=data["country"],
            msisdn=data["msisdn"],
            capabilities=data["features"],
            number_type=data["type"],
            rental_price=data.get("cost", None),
        )._asdict()

    def __init__(self):
        SMSService.__init__(
            self, client=NexmoClient(key=settings.NEXMO["KEY"], secret=settings.NEXMO["SECRET"])
        )

    def perform_send(self, to, text, _from=settings.NEXMO["DEFAULT_FROM"]):
        response = self.client.send_message(
            {
                "from": _from.lstrip("+"),
                "to": settings.NEXMO["TO"] if "TO" in settings.NEXMO else to,
                "text": text,
            }
        )
        response = response["messages"][0]
        if response["status"] != "0":
            raise ServiceError(response["error-text"])
        sid = response["message-id"]
        return (response, sid)

    def get_numbers(self, **kwargs):
        response = self.client.get_account_numbers(kwargs)
        resp_json = json.loads(response)
        logger.debug(resp_json)
        return self.to_internal_phone_numbers(resp_json)

    def search_available_numbers(
        self, country_code: str, capabilities: list, phone_type: PhoneType, pattern: str, **kwargs
    ):
        response = self.client.get_available_numbers(
            country_code=country_code,
            features=capabilities,
            type=phone_type,
            pattern=pattern,
            search_pattern=kwargs.get("search_pattern", 0),
            **kwargs,
        )
        resp_json = json.loads(response)
        logger.debug(resp_json)
        return self.to_internal_phone_numbers(resp_json)

    def purchase_number(self, country_code: str, msisdn: str, **kwargs):
        response = self.client.buy_number(country=country_code, msisdn=msisdn, **kwargs)
        return response

    def cancel_number(self, country_code: str, msisdn: str, **kwargs):
        response = self.client.cancel_number(country=country_code, msisdn=msisdn, **kwargs)
        return response

    def update_number(self, country_code: str, msisdn: str, **kwargs):
        response = self.client.update_number(country=country_code, msisdn=msisdn, **kwargs)
        return response


class TwilioService(SMSService):
    def __init__(self):
        SMSService.__init__(
            self,
            settings.TWILIO["FROM"],
            TwilioClient(settings.TWILIO["ACCOUNT"], settings.TWILIO["TOKEN"]),
        )

    def perform_send(self, to, text):
        try:
            message = self.client.messages.create(from_=self._from, to=to, body=text)
        except TwilioRestException as e:
            raise ServiceError() from e
        return (message, message.sid)

    @staticmethod
    def validate_request(request):
        validator = RequestValidator(settings.TWILIO["TOKEN"])
        return validator.validate(
            request.build_absolute_uri(),
            request.POST,
            request.META.get("HTTP_X_TWILIO_SIGNATURE", ""),
        )

from enum import auto

from cozmo_common.enums import ChoicesEnum, RegularIntChoicesEnum, IntChoicesEnum
from rental_integrations.airbnb.choices import AutoName


class MessageType(RegularIntChoicesEnum):
    email = auto()
    email_managed = auto()
    sms = auto()
    phone = auto()
    api = auto()


class NexmoMessageType(AutoName, ChoicesEnum):
    text = auto()
    unicode = auto()
    binary = auto()


class DeliveryStatus(RegularIntChoicesEnum):
    not_started = auto()
    started = auto()
    delivered = auto()
    not_delivered = auto()
    failed = auto()


class Status(IntChoicesEnum):
    init = 1
    started = 2
    pending = 3
    completed = 4
    error = 5
    queue = 6

from enum import auto

from cozmo_common.enums import ChoicesEnum, RegularIntChoicesEnum


class TemplateTypes(ChoicesEnum):
    Email = "E"
    Message = "M"


class ReservationEvent(RegularIntChoicesEnum):
    BOOKING = auto()
    CANCELLATION = auto()
    CHECK_IN = auto()
    CHECK_OUT = auto()
    MESSAGE = auto()
    CHANGE = auto()


class TransportMethod(RegularIntChoicesEnum):
    EMAIL = auto()
    SMS = auto()
    MESSAGE = auto()
    # will automatically choose the best method first. Assumption: MESSAGE, EMAIL
    AUTO = auto()


class Recipient(RegularIntChoicesEnum):
    GUEST = auto()
    OWNER = auto()
    OTHER = auto()

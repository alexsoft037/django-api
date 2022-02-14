from enum import auto

from cozmo_common.enums import RegularIntChoicesEnum


class RecipientType(RegularIntChoicesEnum):
    guest = auto()
    email = auto()

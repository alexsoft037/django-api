from enum import auto

from cozmo_common.enums import IntChoicesEnum


class ChatSetting(IntChoicesEnum):

    """
    Don't issue a response for this query
    """
    DISABLED = auto()

    """
    Always automatically check and give a yes/or no response
    """
    AUTO_ALWAYS = auto()

    """
    Always respond with a "I will ask" response
    """
    ASK_ALWAYS = auto()

    """
    Always respond with a negative response
    """
    NO_ALWAYS = auto()

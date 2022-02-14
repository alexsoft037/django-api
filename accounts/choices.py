from enum import auto

from cozmo_common.enums import IntChoicesEnum


class ApplicationTypes(IntChoicesEnum):
    iCal_Magic = auto()
    Reservation = auto()
    Owners = auto()
    Vendors = auto()
    Messages = auto()


class RoleTypes(IntChoicesEnum):
    # Can manage and delete organization and users
    owner = auto()

    # Can manage organization and users
    admin = auto()

    # Can read and write all data besides users
    contributor = auto()

    # same as contributor, but is only able to view property data within a property group
    contributor_group = auto()

    # cleaner
    cleaner = auto()

    # property owner
    property_owner = auto()

    # Can access API and read all data besides organization and users
    developer = auto()

    # Can read properties calendars
    contractor = auto()

    # Can read all data besides organization and users
    analyst = auto()

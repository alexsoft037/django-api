from enum import auto

from cozmo_common.enums import IntChoicesEnum


class AirbnbApprovalStatus(IntChoicesEnum):
    ready_for_review = auto()
    approved = auto()
    rejected = auto()
    new = auto()


class AirbnbListingStatus(IntChoicesEnum):
    @property
    def pretty_name(self):
        return self.name

    listed = auto()
    unlisted = auto()


class AirbnbSyncCategory(IntChoicesEnum):
    @property
    def pretty_name(self):
        return self.name

    """
    All listing data is synced via your application. Hosts cannot modify listing details, pricing
    or availability on the Airbnb website.
    """
    sync_all = auto()
    """
    Only pricing and availability data is synced via your application. Hosts can modify listing
    details on the Airbnb website, but not pricing and availability data.
    """
    sync_rates_and_availability = auto()
    """
    All listing data is synced via your application, but the listing cannot be published. The sync
    category must be updated to Everything or Limited in order for the listing to be published.
    """
    sync_undecided = auto()

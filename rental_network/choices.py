from enum import Enum, auto

from app_marketplace.choices import AirbnbSyncCategory
from cozmo_common.enums import ChoicesEnum, IntChoicesEnum

SynchronizationCategory = AirbnbSyncCategory


class AutoName(str, Enum):
    def _generate_next_value_(name, start, count, last_values):
        return name


class Beds(str, ChoicesEnum):
    def _generate_next_value_(name, start, count, last_values):
        return name.lower()

    King_Size = auto()
    Queen_Size = auto()
    Double_Bed = auto()
    Single_Bed = auto()
    Sofa_Bed = auto()
    Couch = auto()
    Air_Mattress = auto()
    Bunk_Bed = auto()
    Floor_Mattress = auto()
    Toddler_Bed = auto()
    Crib = auto()
    Water_Bed = auto()
    Hammock = auto()


class Checkin(AutoName, ChoicesEnum):
    doorman_entry = auto()
    lockbox = auto()
    smartlock = auto()
    keypad = auto()
    host_checkin = auto()
    other_checkin = auto()


class PhotoType(str, ChoicesEnum):
    jpeg = "image/jpeg"
    jpg = "image/jpg"
    png = "image/png"
    gif = "image/gif"

    @classmethod
    def choices(cls):
        return tuple((field.value, field.value) for field in cls)


class PropertyType(AutoName, ChoicesEnum):
    aparthotel = auto()
    apartment = auto()
    barn = auto()
    bed_and_breakfast = "bnb"
    boat = auto()
    boutique_hotel = auto()
    bungalow = auto()
    cabin = auto()
    campsite = auto()
    casa_particular = auto()
    castle = auto()
    cave = auto()
    chalet = auto()
    condominium = auto()
    cottage = auto()
    cycladic_house = auto()
    dammuso = auto()
    dome_house = auto()
    earthhouse = auto()
    farm_stay = auto()
    guest_suite = auto()
    guesthouse = auto()
    heritage_hotel = auto()
    hostel = auto()
    hotel = auto()
    house = auto()
    houseboat = auto()
    hut = auto()
    igloo = auto()
    island = auto()
    lighthouse = auto()
    lodge = auto()
    loft = auto()
    minsu = auto()
    pension = auto()
    plane = auto()
    resort = auto()
    rv = auto()
    ryokan = auto()
    serviced_apartment = auto()
    shepherds_hut = auto()
    tent = auto()
    tiny_house = auto()
    tipi = auto()
    townhouse = auto()
    train = auto()
    treehouse = auto()
    trullo = auto()
    villa = auto()
    windmill = auto()
    yurt = auto()


class StatusCategory(AutoName, ChoicesEnum):
    new = auto()
    ready_for_review = auto()
    approved = auto()
    rejected = auto()


class ReservationStatus(AutoName, ChoicesEnum):
    new = auto()
    accept = auto()
    deny = auto()
    pending = auto()
    timeout = auto()
    pending_voided = auto()
    pending_payment = auto()
    cancelled_by_admin = auto()
    cancelled_by_host = auto()
    cancelled_by_guest = auto()
    at_checkpoint = auto()
    checkpoint_voided = auto()


class CancellationPolicy(AutoName, ChoicesEnum):
    flexible = auto()
    moderate = auto()
    strict = auto()
    strict_14_with_grace_period = auto()
    super_strict_30 = auto()
    super_strict_60 = auto()
    long_term = auto()
    long_term_grace_period = auto()
    # Used in italy only
    flexible_new = auto()
    moderate_new = auto()
    strict_new = auto()
    strict_14_with_grace_period_new = auto()
    super_strict_30_new = auto()
    super_strict_60_new = auto()


class ChannelType(IntChoicesEnum):
    airbnb = 0
    bookingcom = 1
    tripadvisor = 2
    homeaway = 3


class ChannelStatus(IntChoicesEnum):
    """
    Specifies the active status of a channel
    """

    disabled = 0
    enabled = 1
    suspended = 2


class ListingStatus(IntChoicesEnum):
    """
    Specifies the known state of a listing on a channel
    """

    # Listing is live and accepting bookings
    listed = auto()
    # Listing is not accepting bookings
    unlisted = auto()
    # Visible but not accepting bookings
    blocked = auto()
    pending = auto()
    init = auto()
    failed_publish = auto()


class ListingApprovalStatus(IntChoicesEnum):
    """
    Specifies the approval state of a listing. A channel may approve a listing,
    depending on requirements and can take different amounts of time.
    """

    new = auto()
    not_ready = auto()
    # Listing is ready to be reviewed and uploaded
    ready_for_review = auto()
    # Listing has been approved. For channels with no approval status, this is
    # is set to approved if successfully listed
    approved = auto()
    # Listing has been rejected
    rejected = auto()


class ListingSyncScope(IntChoicesEnum):
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


class ListingRequirements(IntChoicesEnum):
    # listing does not have minimum number of photos to be listed by channel
    photos = auto()
    # listing does not have min number of amenities to be listed by channel
    amenities = auto()
    # listing does not have enough high quality photos
    hd_photos = auto()
    # listing does not have enough content in description
    description = auto()
    # listing does not meet or did not provide permit requirements for city
    permits = auto()

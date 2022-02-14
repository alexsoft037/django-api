from enum import Enum, auto

from iso3166 import countries_by_alpha2

from app_marketplace.choices import AirbnbSyncCategory
from cozmo_common.enums import (
    ChoicesEnum,
    IntChoicesEnum,
    RegularChoicesMixin,
    RegularValuesChoicesMixin,
)

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


class RoomType(AutoName, RegularChoicesMixin):
    private_room = auto()
    shared_room = auto()
    entire_home = auto()


class StatusCategory(AutoName, ChoicesEnum):
    new = auto()
    ready_for_review = auto()
    approved = auto()
    rejected = auto()


CountryCode = ChoicesEnum(
    "CountryCode", {code: country.alpha2 for code, country in countries_by_alpha2.items()}
)


class BedType(AutoName, ChoicesEnum):
    king_bed = auto()
    queen_bed = auto()
    double_bed = auto()
    single_bed = auto()
    sofa_bed = auto()
    couch = auto()
    air_mattress = auto()
    bunk_bed = auto()
    floor_mattress = auto()
    toddler_bed = auto()
    crib = auto()
    water_bed = auto()
    hammock = auto()


class RoomAmenity(AutoName, ChoicesEnum):
    """
    en_suite_bathroom is only supported by Airbnb currently
    """

    en_suite_bathroom = auto()


class Amenity(AutoName, RegularValuesChoicesMixin):
    # Common
    essentials = auto()
    kitchen = auto()
    ac = auto()
    heating = auto()
    hair_dryer = "hair-dryer"
    hangers = auto()
    iron = auto()
    washer = auto()
    dryer = auto()
    hot_water = auto()
    tv = auto()
    cable = auto()
    fireplace = auto()
    private_entrance = "private-entrance"
    private_living_room = "private-living-room"
    lock_on_bedroom_door = auto()
    shampoo = auto()
    bed_linens = auto()
    extra_pillows_and_blankets = auto()
    wireless_internet = auto()
    # "internet' is deprecated and should be mapped to 'wireless_internet'
    internet = auto()
    all_night_checkin = "24hr-checkin"
    event_friendly = auto()

    ethernet_connection = auto()
    pocket_wifi = auto()
    laptop_friendly = "laptop-friendly"
    # Kitchen
    microwave = auto()
    coffee_maker = auto()
    refrigerator = auto()
    dishwasher = auto()
    dishes_and_silverware = auto()
    cooking_basics = auto()
    oven = auto()
    stove = auto()
    # Facility
    free_parking = auto()
    street_parking = auto()
    paid_parking = auto()
    paid_parking_on_premises = auto()
    ev_charger = auto()
    gym = auto()
    pool = auto()
    jacuzzi = auto()
    single_level_home = auto()
    # Outdoor
    bbq_area = auto()
    patio_or_balcony = auto()
    garden_or_backyard = auto()
    # Special
    breakfast = auto()
    beach_essentials = auto()
    # Logistics
    luggage_dropoff_allowed = auto()
    long_term_stays_allowed = auto()
    cleaning_before_checkout = auto()
    # Home Safety
    fire_extinguisher = auto()
    carbon_monoxide_detector = auto()
    smoke_detector = auto()
    first_aid_kit = auto()
    # Location
    beachfront = auto()
    lake_access = auto()
    ski_in_ski_out = auto()
    waterfront = auto()
    # Family
    baby_bath = auto()
    baby_monitor = auto()
    babysitter_recommendations = auto()
    bathtub = auto()
    changing_table = auto()
    childrens_books_and_toys = auto()
    childrens_dinnerware = auto()
    crib = auto()
    fireplace_guards = auto()
    game_console = auto()
    high_chair = auto()
    outlet_covers = auto()
    pack_n_play_travel_crib = auto()
    room_darkening_shades = auto()
    stair_gates = auto()
    table_corner_guards = auto()
    window_guards = auto()
    # Accessibility Inside Home
    wide_hallway_clearance = auto()
    # Accessibility Getting Home
    home_step_free_access = auto()
    elevator = auto()
    path_to_entrance_lit_at_night = auto()
    home_wide_doorway = auto()
    flat_smooth_pathway_to_front_door = auto()
    disabled_parking_spot = auto()
    # Accessibility Bedroom
    bedroom_step_free_access = auto()
    wide_clearance_to_bed = auto()
    bedroom_wide_doorway = auto()
    accessible_height_bed = auto()
    electric_profiling_bed = auto()
    # Accessibility Bathroom
    bathroom_step_free_access = auto()
    grab_rails_in_shower = auto()
    grab_rails_in_toilet = auto()
    accessible_height_toilet = auto()
    rollin_shower = auto()
    shower_chair = auto()
    bathroom_wide_doorway = auto()
    tub_with_shower_bench = auto()
    wide_clearance_to_shower_and_toilet = auto()
    handheld_shower_head = auto()
    # Accessibility Common Areas
    common_space_step_free_access = auto()
    common_space_wide_doorway = auto()
    # Accessibility Equipment
    mobile_hoist = auto()
    pool_hoist = auto()
    ceiling_hoist = auto()


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


class PropertyTypeGroup(AutoName, ChoicesEnum):
    """
    Airbnb generalized group of the property types
    """

    apartments = auto()
    bnb = auto()
    boutique_hotels_and_more = auto()
    houses = auto()
    secondary_units = auto()
    unique_homes = auto()


class SharedCategory(AutoName, RegularChoicesMixin):
    host = auto()
    family_friends_roommates = auto()
    other_guests = auto()
    entire_home = auto()


class ListingExpectation(AutoName, ChoicesEnum):
    requires_stairs = auto()
    potential_noise = auto()
    has_pets = auto()
    limited_parking = auto()
    shared_spaces = auto()
    limited_amenities = auto()
    surveillance = auto()
    weapons = auto()
    animals = auto()


class InstantBookingAllowedCategories(AutoName, ChoicesEnum):
    """
    'everyone' is only supported for API connections
    """

    everyone = auto()


class CheckInOutTime(AutoName, RegularValuesChoicesMixin):
    flexible = "FLEXIBLE"


CHECK_IN_FROM_TIME_CHOICES = tuple((str(time), str(time)) for time in range(9, 26))
CHECK_IN_TO_TIME_CHOICES = tuple((str(time), str(time)) for time in range(10, 27))


class CalendarAvailabilityOptions(AutoName, ChoicesEnum):
    """
    Either "available" , "unavailable" or "default". Please use "default" instead
    of "available" if you want the day to comply with any availability rules you set,
    since "available" overwrites all availability rules (e.g. max days notice).
    """

    available = auto()
    unavailable = auto()
    default = auto()


class FeeType(str, RegularValuesChoicesMixin):
    resort_fee = "PASS_THROUGH_RESORT_FEE"
    management_fee = "PASS_THROUGH_MANAGEMENT_FEE"
    community_fee = "PASS_THROUGH_COMMUNITY_FEE"
    linen_fee = "PASS_THROUGH_LINEN_FEE"
    # Not officially in their documentation
    damage_waiver = "PASS_THROUGH_DAMAGE_WAIVER"
    gratuity_fee = "PASS_THROUGH_GRATUITY_FEE"
    service_charge = "PASS_THROUGH_SERVICE_CHARGE"
    # resort_fee = "PASS_THROUGH_OCCUPANCY_BASED_RESORT_FEE"


class AmountType(AutoName, ChoicesEnum):
    percent = auto()
    flat = auto()


class InstantBookingAllowedCategory(AutoName, ChoicesEnum):
    everyone = auto()
    experienced = auto()
    government_id = auto()
    experienced_guest_with_government_id = auto()


class SyncItem(AutoName, ChoicesEnum):
    availability = auto()
    content = auto()
    pricing = auto()
    reservations = auto()
    all = auto()


class MessageRole(AutoName, ChoicesEnum):
    owner = auto()
    guest = auto()
    cohost = auto()
    booker = auto()


class MessageReservationStatus(AutoName, ChoicesEnum):
    pending = auto()
    declined = auto()
    accepted = auto()
    canceled = auto()
    expired = auto()
    unknown = auto()
    awaiting_payment = auto()
    pending_verification = auto()
    checkpoint = auto()


class MessageInquiryStatus(AutoName, ChoicesEnum):
    active = auto()
    declined = auto()
    expired = auto()
    not_possible = auto()
    unknown = auto()


class MessageAttachmentType(AutoName, ChoicesEnum):
    Inquiry = auto()
    SpecialOffer = auto()
    Reservation = auto()


class MessageBusinessPurpose(AutoName, ChoicesEnum):
    booking_direct_thread = auto()  # TODO needs to have undercores


# class Locale(AutoName, ChoicesEnum):
#     id = auto()
#     ms = auto()
#     ca = auto()
#     da = auto()
#     de = auto()
#     en = auto()
#     es = auto()
#     el = auto()
#     fr = auto()
#     hr = auto()
#     it = auto()
#     hu = auto()
#     nl = auto()
#     no = auto()
#     pl = auto()
#     pt = auto()
#     fi = auto()
#     sv = auto()
#     tl = auto()
#     is = auto()
#     cs = auto()
#     ru = auto()
#     he = auto()
#     th = auto()
#     zh = auto()
#     ja = auto()
#     ko = auto()


class ChannelType(IntChoicesEnum):
    airbnb = 0
    bookingcom = 1
    tripadvisor = 2
    homeaway = 3

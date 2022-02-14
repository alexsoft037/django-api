import calendar
import math
import re
from operator import methodcaller

from rest_framework import serializers
from rest_framework.exceptions import ValidationError


def camelize(data):
    """Tansform snake_case keys of input dictionary into camelCase."""

    def underscoreToCamel(match):
        return match.group()[0] + match.group()[2].upper()

    if isinstance(data, dict):
        new_dict = {}
        for key, value in data.items():
            new_key = re.sub(r"[a-z]_[a-z]", underscoreToCamel, key)
            new_dict[new_key] = camelize(value)
        return new_dict
    if isinstance(data, list):
        # also camelize lists of dicts
        for i, element in enumerate(data):
            data[i] = camelize(element)
        return data
    return data


def underscoreize(data):
    """Tansform camelCase keys of input dictionary into snake_case."""
    first_cap_re = re.compile("(.)([A-Z][a-z]+)")
    all_cap_re = re.compile("([a-z0-9])([A-Z])")

    def camel_to_underscore(name):
        s1 = first_cap_re.sub(r"\1_\2", name)
        return all_cap_re.sub(r"\1_\2", s1).lower()

    if isinstance(data, dict):
        new_dict = {}
        for key, value in data.items():
            new_key = camel_to_underscore(key)
            new_dict[new_key] = underscoreize(value)
        return new_dict
    if isinstance(data, list):
        for i, element in enumerate(data):
            data[i] = underscoreize(element)
        return data
    return data


class AddressSerializer(serializers.Serializer):

    address = serializers.CharField(allow_null=True)
    postal_code = serializers.CharField(allow_blank=True, min_length=1, max_length=255)
    latitude = serializers.DecimalField(max_digits=15, decimal_places=10)
    longitude = serializers.DecimalField(max_digits=15, decimal_places=10)
    show_exact_address = serializers.BooleanField()


class BookedRangeSerializer(serializers.Serializer):

    _statuses = ("BOOKED", "RESERVED")

    start = serializers.DateField()
    end = serializers.DateField()
    label = serializers.CharField(read_only=True, required=False)
    status = serializers.ChoiceField(choices=tuple(zip(_statuses, _statuses)))


class DetailSerializer(serializers.Serializer):

    _best_for = ("SHORT_TERM", "LONG_TERM", "HOUSE_SWAP", "CORPORATE", "HENSTAG")
    _car_required = ("NOT_REQUIRED", "RECOMMENDED", "REQUIRED")
    _check_time = (
        "ZERO",
        "ONE",
        "TWO",
        "THREE",
        "FOUR",
        "FIVE",
        "SIX",
        "SEVEN",
        "EIGHT",
        "NINE",
        "TEN",
        "ELEVEN",
        "TWELVE",
        "THIRTEEN",
        "FOURTEEN",
        "FIFTEEN",
        "SIXTEEN",
        "SEVENTEEN",
        "EIGHTEEN",
        "NINETEEN",
        "TWENTY",
        "TWENTY_ONE",
        "TWENTY_TWO",
        "TWENTY_THREE",
        "FLEXIBLE",
    )
    _studio_type = "STUDIO"
    _property_types = (
        "APARTMENT",
        "B_AND_B",
        "BARN",
        "BEACH_HUT",
        "BOATHOUSE",
        "BUNGALOW",
        "CAMPER_VAN",
        "CARAVAN_MOBILE_HOME",
        "CASTLE",
        "CAVE_HOUSE",
        "CHALET",
        "CHATEAU",
        "CONDO",
        "CONVERTED_CHAPEL",
        "COTTAGE",
        "FARMHOUSE",
        "FINCA",
        "FORT",
        "GITE",
        "GUEST_HOUSE",
        "HOTEL_APARTMENT",
        "HOUSE",
        "HOUSEBOAT",
        "LIGHT_HOUSE",
        "LODGE",
        "LOG_CABIN",
        "MANOR_HOUSE",
        "NARROWBOAT",
        "PENT_HOUSE",
        "ROOM",
        "RIAD",
        "SHEPHERDS_HUT",
        "SKI_CHALET",
        _studio_type,
        "TENTED_CAMP",
        "TIPI_TEEPEE",
        "TOWER",
        "TOWNHOUSE",
        "TREE_HOUSE",
        "TRULLO",
        "VILLA",
        "WATERMILL",
        "WINDMILL",
        "YACHT",
        "YURT",
    )

    property_type = serializers.ChoiceField(
        choices=list(zip(_property_types, _property_types)), allow_null=True
    )
    bedrooms = serializers.ListField(serializers.JSONField(required=False))
    bathrooms = serializers.ListField(serializers.JSONField(required=False))
    max_occupancy = serializers.IntegerField(
        min_value=0, max_value=50, required=False, allow_null=True
    )
    rental_best_for = serializers.ListField(
        child=serializers.ChoiceField(choices=list(zip(_best_for, _best_for))), required=False
    )
    check_in_time = serializers.ChoiceField(choices=list(zip(_check_time, _check_time)))
    check_out_time = serializers.ChoiceField(choices=list(zip(_check_time, _check_time)))
    car_required = serializers.ChoiceField(
        allow_null=True, required=False, choices=list(zip(_car_required, _car_required))
    )
    tourist_license_number = serializers.CharField(
        min_length=0, max_length=50, allow_null=True, required=False, allow_blank=True
    )

    def validate(self, data):
        property_type = data.get("property_type", None)
        if "bedrooms" in data:
            # bedroom with ordinal 0 is a special case, listing beds outside bedrooms
            bedrooms_count = len([b for b in data["bedrooms"] if b["ordinal"] > 0])
        else:
            bedrooms_count = math.inf

        if property_type == self._studio_type:
            if bedrooms_count > 0:
                raise ValidationError("`Studio` property cannot have any bedrooms")
        elif bedrooms_count == 0:
            raise ValidationError("Property other than `studio` must have at least one bedroom")

        return data


class iCalSerializer(serializers.Serializer):

    url = serializers.URLField(read_only=True)
    label = serializers.CharField()
    source = serializers.HStoreField


class CalendarSerializer(serializers.Serializer):

    booked_ranges = BookedRangeSerializer(many=True, allow_null=True)
    icals = iCalSerializer(many=True, read_only=True)


class FeeSerializer(serializers.Serializer):

    amount = serializers.DecimalField(max_digits=8, decimal_places=2)
    name = serializers.CharField()
    description = serializers.CharField(required=False)


class LocationSerializer(serializers.Serializer):

    city = serializers.CharField()
    region = serializers.CharField()
    country = serializers.CharField()
    country_code = serializers.CharField(min_length=2, max_length=2)


class NearbyAmenitiesSerializer(serializers.Serializer):

    _types = tuple(
        "area_nearest_{}".format(place)
        for place in ("airport", "amenities", "beach", "ferry", "railway")
    )

    type = serializers.ChoiceField(choices=tuple(zip(_types, _types)))
    distance = serializers.IntegerField(min_value=1)


class PhotoSerializer(serializers.Serializer):

    external_photo_reference = serializers.CharField(min_length=1, max_length=512, allow_null=True)
    url = serializers.URLField()
    caption = serializers.CharField(min_length=1, max_length=255, required=False, allow_null=True)


class DefaultRateSerializer(serializers.Serializer):

    _changeover_days = tuple(map(methodcaller("upper"), calendar.day_name)) + ("FLEXIBLE",)

    nightly_rate = serializers.IntegerField(min_value=0, required=False)
    weekend_rate = serializers.IntegerField(min_value=0, required=False)
    weekly_rate = serializers.IntegerField(min_value=0, required=False)
    monthly_rate = serializers.IntegerField(min_value=0, required=False)
    minimum_stay = serializers.IntegerField(min_value=1, max_value=90, required=False)
    additional_guest_fee_threshold = serializers.IntegerField(
        min_value=0, required=False, allow_null=True
    )
    additional_guest_fee_amount = serializers.IntegerField(
        min_value=0, required=False, allow_null=True
    )
    changeover_day = serializers.ChoiceField(
        choices=tuple(zip(_changeover_days, _changeover_days)), required=False
    )


class SeasonalRateSerializer(DefaultRateSerializer):

    name = serializers.CharField(min_length=1, max_length=100, required=False, allow_blank=True)
    start_date = serializers.DateField()
    end_date = serializers.DateField()


class RatesSerializer(serializers.Serializer):

    _weekend_types = ("NONE", "FRIDAY_SATURDAY", "SATURDAY_SUNDAY", "FRIDAY_SATURDAY_SUNDAY")

    default_rate = DefaultRateSerializer()
    seasonal_rates = SeasonalRateSerializer(many=True, required=False)
    weekend_type = serializers.ChoiceField(
        choices=tuple(zip(_weekend_types, _weekend_types)), required=False
    )
    demage_deposit = serializers.DecimalField(max_digits=15, decimal_places=2, required=False)
    tax_percentage = serializers.DecimalField(
        max_digits=8, decimal_places=5, required=False, min_value=0, max_value=100
    )


class ListingSerializer(serializers.Serializer):
    _allowed_currencies = ("AUD", "CAD", "CHF", "EUR", "GBP", "SEK", "USD", "THB", "NZD")
    _allowed_languages = (
        "en_US",
        "es_ES",
        "en_GB",
        "de_DE",
        "fr_FR",
        "it_IT",
        "sv_SE",
        "pt_PT",
        "nl_NL",
        "tr_TR",
        "el_GR",
        "pt_BR",
        "en_SG",
    )
    _guests_requirements = ("SMOKING", "PETS", "CHILDREN")
    _features = (
        "AIR_CONDITIONING",
        "BALCONY_OR_TERRACE",
        "BEACHFRONT",
        "BEACH_OR_LAKESIDE_RELAXATION",
        "BICYCLES_AVAILABLE",
        "BOAT_AVAILABLE",
        "CABLE_SATELLITE_TV",
        "CEILING_FANS",
        "CENTRAL_HEATING",
        "CHILDRENS_POOL",
        "CITY_GETAWAY",
        "CYCLING_TRIPS",
        "DISHWASHER",
        "DRYER",
        "DVD_PLAYER",
        "ELEVATOR_IN_BUILDING",
        "FIREPLACE",
        "FISHING_NEARBY",
        "FREEZER",
        "GAMES_ROOM",
        "GOLF_NEARBY (1)",
        "GOLF_WITHIN_DRIVE (2)",
        "GRILL",
        "GYM",
        "HEATED_OUTDOOR_POOL_SHARED",
        "HEATED_OUTDOOR_POOL_PRIVATE",
        "HIKING_TRIPS",
        "HORSE_RIDING_NEARBY",
        "HOUSEKEEPING_INCLUDED",
        "INDOOR_POOL_SHARED",
        "INDOOR_POOL_PRIVATE",
        "INTERNET_ACCESS",
        "IRON",
        "JACUZZI_OR_HOT_TUB",
        "KETTLE",
        "LINENS_PROVIDED",
        "MICROWAVE",
        "MOUNTAIN_VIEWS",
        "OCEAN_VIEWS",
        "PATIO",
        "PING_PONG_TABLE",
        "POOL_TABLE",
        "PRIVATE_YARD",
        "PARKING_SPACE",
        "REFRIGERATOR",
        "RURAL_COUNTRYSIDE_RETREATS",
        "SAUNA",
        "SKIING (3)",
        "STAFFED_PROPERTY",
        "STEREO_SYSTEM",
        "SAFE",
        "STOVE",
        "SUNROOF_OR_ROOF_TERRACE",
        "TENNIS_COURTS_NEARBY",
        "TRAMPOLINE",
        "TOASTER",
        "TOWELS_PROVIDED",
        "TV",
        "UNHEATED_OUTDOOR_POOL_SHARED",
        "UNHEATED_OUTDOOR_POOL_PRIVATE",
        "WASHING_MACHINE",
        "WATERFRONT",
        "WATERSPORTS_NEARBY",
        "WATER_VIEWS",
        "WIFI",
    )

    details = DetailSerializer(required=False)
    descriptions = serializers.JSONField(required=False)  # TODO Create serializer
    address = AddressSerializer(required=False)
    location = LocationSerializer(required=False)
    features = serializers.ListField(
        child=serializers.ChoiceField(choices=tuple(zip(_features, _features))), required=False
    )
    nearby_amenities = NearbyAmenitiesSerializer(many=True, required=False)
    guest_requirements = serializers.ListField(
        child=serializers.ChoiceField(
            choices=tuple(zip(_guests_requirements, _guests_requirements))
        ),
        required=False,
    )
    currency = serializers.ChoiceField(
        default="USD", choices=tuple(zip(_allowed_currencies, _allowed_currencies))
    )
    rates = RatesSerializer(allow_null=True, required=False)
    fees = FeeSerializer(many=True, required=False)
    active = serializers.BooleanField()
    calendar = CalendarSerializer(allow_null=True, required=False)
    external_account_reference = serializers.CharField(min_length=1, max_length=512)
    external_listing_reference = serializers.CharField(
        min_length=1, max_length=512, allow_null=True
    )
    listing_reference = serializers.CharField(min_length=1, max_length=512, allow_null=True)
    photos = PhotoSerializer(allow_null=True, many=True, required=False)
    text_language = serializers.ChoiceField(
        allow_null=True,
        write_only=True,
        default="en_US",
        choices=tuple(zip(_allowed_languages, _allowed_languages)),
    )
    url = serializers.URLField(allow_null=True, required=False)

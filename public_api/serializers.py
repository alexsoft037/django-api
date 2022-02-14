from collections import OrderedDict
from datetime import date, timedelta

from rest_framework import serializers
from rest_framework.fields import (
    CharField,
    DateField,
    DecimalField,
    HiddenField,
    IntegerField,
    ReadOnlyField,
    SerializerMethodField,
    URLField,
    empty,
)
from stringcase import camelcase

from cozmo_common.fields import ChoicesField, DefaultOrganization, HourField
from cozmo_common.functions import date_range
from cozmo_common.serializers import ValueFormattedSerializer
from crm.models import Contact
from listings import choices, fields, models, serializers as l_serializers, services


def _model_serializer(Model, *, exclude=None):
    """Generate a model serializer instance for a reverse reference."""
    if exclude is None:
        exclude = ["id"]

    Meta = type("Meta", (object,), {"model": Model, "exclude": exclude})
    NewSerializer = type(
        Model.__name__ + "Serializer", (serializers.ModelSerializer,), {"Meta": Meta}
    )
    return NewSerializer


BasicAmenitiesSerializer = _model_serializer(
    models.BasicAmenities,
    exclude=[
        "id",
        "prop",
        "wifi_ssid",
        "wifi_password",
        "dogs_allowed",
        "cats_allowed",
        "large_dogs_allowed",
        "laundry_type",
        "parking_fee",
        "parking_type",
        "parking_description"
    ],
)


FeatureSerializer = _model_serializer(models.Feature, exclude=["id"])


class SuitabilitySerializer(serializers.ModelSerializer):

    serializer_choice_field = ChoicesField

    class Meta:
        model = models.Suitability
        exclude = ("id", "prop")


class ImageRawSerializer(serializers.Serializer):

    url = fields.StorageUrlField()
    width = SerializerMethodField()
    height = SerializerMethodField()

    def get_width(self, obj):
        return self._get_dimension(obj, "width")

    def get_height(self, obj):
        return self._get_dimension(obj, "height")

    def _get_dimension(self, obj, attr):
        try:
            dimension = getattr(obj, attr)
        except FileNotFoundError:
            dimension = None
        except RuntimeError:  # Bug in WebP handling https://code.djangoproject.com/ticket/29705
            dimension = None
        return dimension


class ImageSerializer(serializers.ModelSerializer):

    download_urls = SerializerMethodField()

    class Meta:
        model = models.Image
        fields = ("id", "sort_order", "caption", "download_urls")
        extra_kwargs = {"sort_order": {"source": "order"}}

    def get_download_urls(self, obj):
        return {"raw": ImageRawSerializer(instance=obj.url).data}


class PropertySerializer(serializers.ModelSerializer):

    suitability = SuitabilitySerializer()
    check_in_time = HourField(source="booking_settings.check_in_out.check_in_from", default=None)
    check_out_time = HourField(
        source="booking_settings.check_in_out.check_out_until", default=None
    )
    latitude = DecimalField(
        source="location.latitude", default=None, max_digits=15, decimal_places=12
    )
    longitude = DecimalField(
        source="location.longitude", default=None, max_digits=15, decimal_places=12
    )
    continent = CharField(source="location.continent", default=None)
    country = CharField(source="location.country", default=None)
    region = CharField(source="location.region", default=None)
    state = CharField(source="location.state", default=None)
    city = CharField(source="location.city", default=None)
    address1 = CharField(source="location.address", default=None)
    address2 = CharField(source="location.apartment", default=None)
    postal_code = CharField(source="location.postal_code", default=None)
    images = SerializerMethodField()
    amenities = SerializerMethodField()
    custom_amenities = SerializerMethodField()
    ical_url = CharField(source="cozmo_calendar.url", default=None)
    bathrooms = DecimalField(max_digits=3, decimal_places=1)
    bedrooms = DecimalField(max_digits=3, decimal_places=1)
    is_available = SerializerMethodField()
    full_address = ReadOnlyField()
    currency = ChoicesField(
        source="pricing_settings.currency",
        choices=choices.Currencies,
        default=choices.Currencies.USD.pretty_name,
    )
    description = SerializerMethodField()
    headline = SerializerMethodField()
    accommodates = IntegerField(source="max_guests")

    rooms = l_serializers.RoomSerializer(many=True, source="room_set")
    months_advanced_bookable = IntegerField(source="booking_settings.months_advanced_bookable")
    default_min_nights = IntegerField(source="availability_settings.min_stay")
    default_max_nights = IntegerField(source="availability_settings.max_stay")
    booking_lead_time = IntegerField(source="availability_settings.advance_notice")
    preparation_time = IntegerField(source="availability_settings.preparation")
    default_nightly_price = CharField(source="pricing_settings.nightly")
    cleaning_fee = CharField(source="pricing_settings.cleaning_fee")
    security_deposit = CharField(source="pricing_settings.security_deposit")
    extra_person_fee = CharField(source="pricing_settings.extra_person_fee")
    included_guests = IntegerField(source="pricing_settings.included_guests")

    _nested_related = {"rooms": l_serializers.RoomSerializer, "suitability": SuitabilitySerializer}

    serializer_choice_field = ChoicesField

    class Meta:
        model = models.Property
        fields = (
            "id",
            "name",
            "headline",
            "bathrooms",
            "bedrooms",
            "accommodates",
            "description",
            "currency",
            "check_in_time",
            "check_out_time",
            "latitude",
            "longitude",
            "months_advanced_bookable",
            "suitability",
            "property_type",
            "room_type",
            "status",
            "address1",
            "address2",
            "postal_code",
            "continent",
            "country",
            "region",
            "state",
            "city",
            "amenities",
            "custom_amenities",
            "ical_url",
            "images",
            "date_updated",
            "is_available",
            "legacy_id",
            "full_address",
            "max_guests",
            "default_min_nights",
            "default_max_nights",
            "booking_lead_time",
            "preparation_time",
            "default_nightly_price",
            "cleaning_fee",
            "security_deposit",
            "extra_person_fee",
            "included_guests",
            "rooms",
        )
        extra_kwargs = {"room_type": {"source": "rental_type"}}

    def _get_combined_description(self, desc):
        assert desc is not None, "Description obj should not be null"
        return desc.combined_descriptions

    def get_description(self, obj):
        if obj.descriptions.description:
            return obj.descriptions.description
        return self._get_combined_description(obj.descriptions)

    def get_headline(self, obj):
        # TODO consider enforcing headline entry vs name
        if obj.descriptions.headline:
            return obj.descriptions.headline
        return obj.descriptions.name

    def get_amenities(self, obj):
        amenities = list()

        if hasattr(obj, "basic_amenities"):
            b_amenities = BasicAmenitiesSerializer(obj.basic_amenities)
            amenities = {camelcase(key): value for key, value in b_amenities.data.items()}
        return amenities

    def get_custom_amenities(self, obj):
        amenities = list()
        if obj.features:
            custom_amenities = FeatureSerializer(obj.features, many=True)
            amenities = [a["name"] for a in custom_amenities.data if a["value"]]
        return amenities

    def get_images(self, obj):
        return ImageSerializer(many=True, instance=obj.image_set.self_hosted()).data

    def get_is_available(self, obj):
        return obj.status == models.Property.Statuses.Active.value

    def validate(self, data):
        for field, serializer_class in {**self._nested_fields, **self._nested_related}.items():
            if field in data:
                instance = getattr(self.instance, field, None)
                serializer = serializer_class(instance, data=data[field], partial=bool(instance))
                serializer.is_valid(raise_exception=True)
                data[field] = serializer
        return data


class RentalMinimalSerializer(serializers.ModelSerializer):

    serializer_choice_field = ChoicesField

    class Meta:
        model = models.Property
        fields = ("id", "status", "date_updated")

    allowed_formats = {"legacy": "legacy_id"}

    def _create_property_field(self, field_name):
        model = getattr(self.Meta, "model")
        field_class, field_kwargs = self.build_property_field(field_name, model)

        return {field_name: field_class(**field_kwargs)}

    def __init__(self, *args, **kwargs):
        format = kwargs.get("context").get("request").query_params.get("_format")

        super(RentalMinimalSerializer, self).__init__(*args, **kwargs)

        format_field_name = self.allowed_formats.get(format)
        if format_field_name:
            self.fields.update(self._create_property_field(format_field_name))


class GuestSerializer(serializers.ModelSerializer):

    avatar = URLField(required=False)
    organization = HiddenField(default=DefaultOrganization())

    class Meta:
        model = Contact
        exclude = ("external_id",)


class ReservationRateSerializer(ValueFormattedSerializer):
    amount_formatted = serializers.SerializerMethodField("get_value_formatted")

    class Meta:
        model = models.ReservationRate
        fields = ("amount", "amount_formatted", "duration")
        extra_kwargs = {"amount": {"source": "value"}}


class ReservationFeeSerializer(ValueFormattedSerializer):
    amount_formatted = serializers.SerializerMethodField("get_value_formatted")

    class Meta:
        model = models.ReservationFee
        fields = (
            "amount",
            "amount_formatted",
            "fee_tax_type",
            "name",
            "optional",
            "refundable",
            "taxable",
        )
        extra_kwargs = {"fee_tax_type": {"default": empty}, "amount": {"source": "value"}}


class ReservationDiscountSerializer(ValueFormattedSerializer):
    amount_formatted = serializers.SerializerMethodField("get_value_formatted")

    class Meta:
        model = models.ReservationDiscount
        fields = ("discount_type", "amount", "amount_formatted", "optional")
        extra_kwargs = {"amount": {"source": "value"}}


class ReservationSerializer(l_serializers.ReservationSerializer):

    guest = GuestSerializer(required=False)
    discounts = ReservationDiscountSerializer(
        many=True, required=False, source="reservationdiscount_set"
    )
    fees = ReservationFeeSerializer(many=True, required=False, source="reservationfee_set")
    rate = SerializerMethodField()
    prop = None

    def get_rate(self, obj):
        currency_symbol = choices.Currencies[obj.prop.pricing_settings.currency].symbol
        return {
            "amount": str(obj.nightly_price),
            "amountFormatted": f"{currency_symbol}{obj.nightly_price}",
            "duration": obj.nights,
        }

    class Meta:
        model = models.Reservation
        fields = (
            "prop",
            "guest",
            "discounts",
            "fees",
            "rate",
            "start_date",
            "end_date",
            "status",
            "currency",
            "base_total",
            "nightly_price",
            "price",
            "price_formatted",
            "paid",
            "guests_adults",
            "guests_children",
            "guests_infants",
            "pets",
            "external_id",
            "confirmation_code",
            "date_created",
            "date_updated",
            "organization",
            "nights",
        )
        read_only_fields = ("confirmation_code",)
        extra_kwargs = {"price": {"required": False, "allow_null": True}}


class StayRequirementsSerializer(serializers.ModelSerializer):
    start_date = DateField(source="time_frame.lower", default=None)
    end_date = DateField(source="time_frame.upper", default=None)

    class Meta:
        model = models.Availability
        fields = [
            "id",
            "start_date",
            "end_date",
            "min_age",
            "min_stay",
            "max_stay",
            "preparation",
            "advance_notice",
            "window",
        ]
        extra_kwargs = {"window": {"source": "booking_window_months"}}


class RateSerializer(serializers.ModelSerializer):
    start_date = DateField(source="time_frame.lower", default=None)
    end_date = DateField(source="time_frame.upper", default=None)
    extra_person = DecimalField(
        source="extra_person_fee", max_digits=9, decimal_places=2, required=False, default=0
    )

    class Meta:
        model = models.Rate
        exclude = (
            "time_frame",
            "prop",
            "date_updated",
            "date_created",
            "label",
            "seasonal",
            "extra_person_fee",
            "cleaning_fee",
            "security_deposit",
            "currency",
            "smart"
        )


class FeeSerializer(serializers.ModelSerializer):
    serializer_choice_field = ChoicesField

    class Meta:
        model = models.AdditionalFee

        fields = (
            "id",
            "name",
            "value",
            "fee_tax_type",
            "optional",
            "taxable",
            "refundable",
            "calculation_method",
        )
        extra_kwargs = {"calculation_method": {"default": empty}}


class AvailabilityCalendarSerializer(serializers.BaseSerializer):
    def to_representation(self, instance):
        count = self.context["request"].query_params.get("count")
        currency = getattr(
            instance.pricing_settings, "currency", choices.Currencies.USD.pretty_name
        )
        if not count or not count.isnumeric():
            count = 180
        start = date.today()
        end = start + timedelta(days=int(count))

        rates = models.Rate.rate_per_day(start, end, instance.id)
        availability = models.Availability.availability_per_day(start, end, instance.id)

        ipa = services.IsPropertyAvailable(instance, start, end)
        ipa.run_check()

        blocked_days = []
        for b in ipa.blocked_days:
            blocked_days += [day for day in date_range(b.get("start_date"), b.get("end_date"))]

        calendar = []
        for d in date_range(start, end):
            # If property does not have rates is unavailable
            available = True
            if rates[d]:
                price = rates[d].nightly
                priceFormatted = "{0}{1}".format(choices.Currencies[currency].symbol, price)
            else:
                price, priceFormatted, available = None, None, False
            min_nights = availability[d].min_stay if availability.get(d) else None
            calendar.append(
                {
                    "date": d,
                    "available": available and d not in blocked_days,
                    "min_nights": min_nights,
                    "price": price,
                    "price_formatted": priceFormatted,
                }
            )

        return OrderedDict([("count", count), ("currency", currency), ("calendar", calendar)])

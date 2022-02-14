import logging

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import IntegerField, Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.fields import (
    BooleanField,
    CharField,
    DecimalField,
    HiddenField,
    NullBooleanField,
    ReadOnlyField,
    SerializerMethodField,
    URLField,
    empty,
)
from rest_framework.relations import PrimaryKeyRelatedField
from rest_framework.serializers import ListSerializer, ModelSerializer, Serializer
from titlecase import titlecase

from accounts.models import OwnerUser
from accounts.signals import property_activated
from cozmo_common import fields, serializers as common_ser
from cozmo_common.serializers import ValueFormattedSerializer
from crm.models import Contact  # XXX COZ-557 Remove after front end adapts
from listings.mappings import features_syn_rev, suitability_rev
from listings.models import ReservationNote, Suitability
from listings.services import IsPropertyAvailable
from listings.signals import property_changed
from owners.models import Owner
from owners.serializers import OwnerForPropertyListSerializer, OwnerSerializer
from payments.models import Charge
from payments.serializers import GuestCreditCardSerializer
from pois.models import YelpCategories
from rental_integrations.airbnb.models import AirbnbSync
from rental_integrations.serializers import ChannelSyncBasicSerializer
from rental_network.models import LongTermRentalSettings
from send_mail.models import Conversation
from send_mail.serializers import ConversationSerializer
from . import models
from .calendars.serializers import CalendarSerializer
from .choices import (
    CancellationReasons,
    FeeTypes,
    PropertyStatuses,
    PropertyTypes,
    Rentals,
    ReservationStatuses,
    TaxTypes,
)
from .fields import DateRangeField, StorageUrlField
from .tasks import fetch_property_media

logger = logging.getLogger(__name__)


def _model_serializer(Model, *, exclude=None):
    """Generate a model serializer instance for a reverse reference."""
    if exclude is None:
        exclude = ["id"]

    Meta = type("Meta", (object,), {"model": Model, "exclude": exclude})
    NewSerializer = type(Model.__name__ + "Serializer", (ModelSerializer,), {"Meta": Meta})
    return NewSerializer


CheckInOutSerializer = _model_serializer(models.CheckInOut)

CoordinatesSerializer = _model_serializer(models.Coordinates)

PricingSettingsSerializer = _model_serializer(
    models.PricingSettings, exclude=["id", "date_created", "date_updated", "prop"]
)

AvailabilitySettingsSerializer = _model_serializer(
    models.AvailabilitySettings, exclude=["id", "date_created", "date_updated", "prop"]
)

ListingDescriptionSerializer = _model_serializer(
    models.ListingDescriptions, exclude=["id", "date_created", "date_updated", "prop"]
)

GroupUserAssignmentSerializer = _model_serializer(
    models.GroupUserAssignment, exclude=["id", "date_created", "date_updated", "user"]
)

ExternalListingSerializer = _model_serializer(models.ExternalListing)


class PropertyExternalListingSerializer(ModelSerializer):

    source = CharField(source="get_source_display")

    class Meta:
        model = models.ExternalListing
        fields = ("prop", "id", "url", "source", "listing_id")


class MediaListSerializer(ListSerializer):
    def create(self, validated_data, **kwargs):
        instances = super().create(self._set_order(validated_data, **kwargs))

        if "prop" in kwargs:
            fetch_property_media.delay(kwargs["prop"].pk)

        return instances

    def update(self, instances, validated_data, **kwargs):
        for instance, data in zip(instances, self._set_order(validated_data, **kwargs)):
            self.child.update(instance, data)

        if "prop" in kwargs:
            fetch_property_media.delay(kwargs["prop"].pk)

        return instances

    def _set_order(self, validated_data, **kwargs):
        max_order = getattr(self.child.Meta.model, "ORDER_MAX", 1000)

        def _order_or_default(data):
            return data.get("order", max_order)

        sorted_data = sorted(validated_data, key=_order_or_default)
        for i, data in enumerate(sorted_data):
            data.update(kwargs)
            data["order"] = min(i, max_order)

        return validated_data


class MediaSerializer(ModelSerializer):
    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        self._set_order(instance)
        return instance

    def create(self, validated_data):
        instance = super().create(validated_data)
        self._set_order(instance)
        return instance

    def _set_order(self, instance):
        # Ordering should be without any gaps
        medias = self.Meta.model.objects.filter(prop_id=instance.prop_id).order_by("order", "id")
        with transaction.atomic():
            for i, media in enumerate(medias):
                media.order = i
                media.save()


class TimeFrameValidateMixin:
    def validate_time_frame(self, time_frame):
        if time_frame.lower_inf or time_frame.upper_inf:
            raise ValidationError("Specify both lower and upper dates")
        elif time_frame.isempty:
            raise ValidationError("Cannot be empty")
        elif time_frame.lower > time_frame.upper:
            raise ValidationError("End should occur after start")
        return time_frame


class TimeFrameSerializerMixin(TimeFrameValidateMixin, ModelSerializer):
    time_frame = DateRangeField()

    # TODO here is a problem with "Expected a dictionary of items but got type \"DateRange\"."
    def to_internal_value(self, data):
        time_frame = data.get("time_frame")
        # FIXME In the real request data['time_frame'] is DateRange, in tests dict
        if time_frame is not None and not isinstance(time_frame, dict):
            data["time_frame"] = {"upper": time_frame.upper, "lower": time_frame.lower}
        return super().to_internal_value(data)

    @transaction.atomic
    def create(self, validated_data):
        self._intersect(validated_data)

        validated_data.pop("valid_to", None)
        return super().create(validated_data)

    # TODO This method is never called
    @transaction.atomic
    def update(self, instance, validated_data):
        if "time_frame" in validated_data:
            kwargs = validated_data.copy()
            kwargs.setdefault("prop", instance.prop_id)
            self._intersect(kwargs, instance=instance)
        return super().update(instance, validated_data)

    def get_queryset(self, validated_data):
        Model = self.Meta.model
        # When view is nested instead of prop we will get prop_id
        prop = validated_data.get("prop") or validated_data.get("prop_id")
        return Model.objects.filter(prop=prop)

    def _intersect(self, validated_data, instance=None):
        """Adjust neighbors of a rate."""

        time_frame = validated_data.get("time_frame")

        Model = self.Meta.model
        qs = self.get_queryset(validated_data)

        if instance:
            qs = qs.exclude(pk=instance.pk)

        # Remove all rates which are entirely contained by a new rate
        qs.filter(time_frame__contained_by=time_frame).delete()

        qs = qs.exclude(Q(time_frame__startswith=None) | Q(time_frame__endswith=None))  # FIXME

        # Modify an overlapping rate occurring before a new rate
        try:
            to_move = qs.filter(time_frame__overlap=time_frame, time_frame__lte=time_frame).get()
        except Model.DoesNotExist:
            pass
        else:
            if to_move.time_frame.lower == time_frame.lower:
                to_move.delete()
            elif to_move.time_frame.lower < time_frame.lower and (
                to_move.time_frame.upper > time_frame.upper
            ):

                to_move_upper = to_move.time_frame.upper

                to_move.time_frame = (to_move.time_frame.lower, time_frame.lower)
                to_move.save()

                # New instance after
                to_move.id = None
                to_move.time_frame = (time_frame.upper, to_move_upper)
                to_move.save()
            else:
                to_move.time_frame = (to_move.time_frame.lower, time_frame.lower)
                to_move.save()

        # Modify an overlapping rate occurring after a new rate
        try:
            to_move = qs.filter(time_frame__overlap=time_frame, time_frame__gte=time_frame).get()
        except Model.DoesNotExist:
            pass
        else:
            if time_frame.upper == to_move.time_frame.upper:
                to_move.delete()
            else:
                to_move.time_frame = (time_frame.upper, to_move.time_frame.upper)
                to_move.save()


class FeeTaxSerializerMixin:

    serializer_choice_field = fields.ChoicesField

    def __init__(self, *args, prop_required=False, **kwargs):
        self.Meta.extra_kwargs["prop"]["required"] = prop_required
        super().__init__(*args, **kwargs)


class BlockingSerializer(TimeFrameValidateMixin, ModelSerializer):
    time_frame = DateRangeField()

    class Meta:
        model = models.Blocking
        exclude = ["prop"]


class BookingSettingsSerializer(ModelSerializer):
    serializer_choice_field = fields.ChoicesField

    check_in_out = CheckInOutSerializer(required=False, allow_null=True)

    class Meta:
        model = models.BookingSettings
        fields = (
            "months_advanced_bookable",
            "instant_booking_allowed",
            "instant_booking_welcome",
            "cancellation_policy",
            "check_in_out",
        )

    def create(self, validated_data):
        check_in_out = validated_data.pop("check_in_out", None)

        instance = super().create(validated_data)

        if check_in_out:
            instance.check_in_out = models.CheckInOut.objects.create(**check_in_out)
            instance.save()
        return instance

    def update(self, instance, validated_data):
        check_in_out = validated_data.pop("check_in_out", None)

        if check_in_out:
            check_in_out_instance, _ = models.CheckInOut.objects.update_or_create(
                bookingsettings=instance, defaults=check_in_out
            )
            instance.check_in_out = check_in_out_instance

        return super().update(instance, validated_data)


class DiscountSerializer(ModelSerializer):

    serializer_choice_field = fields.ChoicesField

    class Meta:
        model = models.Discount
        fields = (
            "id",
            "type",
            "days_before",
            "value",
            "is_percentage",
            "optional",
            "calculation_method",
            "prop",
        )
        extra_kwargs = {"type": {"source": "discount_type", "default": empty}}

    def validate(self, data):
        def get_data(key):
            return data.get(key, getattr(self.instance, key, None))

        is_percentage = get_data("is_percentage")
        value = get_data("value")

        if is_percentage and not (0 < value <= 100):
            raise ValidationError("Percentage value must be in range (0, 100]")

        return data


class FeeSerializer(FeeTaxSerializerMixin, ModelSerializer):
    class Meta:
        model = models.Fee
        fields = (
            "id",
            "name",
            "value",
            "type",
            "optional",
            "taxable",
            "refundable",
            "order",
            "calculation_method",
            "is_percentage",
            "prop",
        )
        extra_kwargs = {
            "type": {
                "source": "fee_tax_type",
                "choices": FeeTypes.choices(),
                "default": empty,
                "required": False,
            },
            "calculation_method": {"default": empty, "required": False},
            "prop": {"required": False},
        }


class GuestSerializer(ModelSerializer):

    avatar = URLField(required=False)
    organization = HiddenField(default=fields.DefaultOrganization())
    credit_cards = GuestCreditCardSerializer(many=True, allow_null=True, required=False)

    class Meta:
        model = Contact
        exclude = ("external_id",)


class GuestMinimalSerializer(GuestSerializer):
    class Meta:
        model = Contact
        fields = ("first_name", "last_name", "avatar")


class ImageSerializer(MediaSerializer):
    class Meta:
        model = models.Image
        fields = ("id", "url", "thumbnail", "caption", "order")
        extra_kwargs = {"thumbnail": {"read_only": True}}

    def create(self, validated_data):
        instance = super().create(validated_data)
        instance.generate_thumbnail()
        return instance


class ImageUrlSerializer(MediaSerializer):

    url = StorageUrlField()

    class Meta:
        model = models.Image
        fields = ("id", "url", "thumbnail", "caption", "order")
        extra_kwargs = {"thumbnail": {"read_only": True}}
        list_serializer_class = MediaListSerializer


class VideoSerializer(MediaSerializer):
    class Meta:
        model = models.Video
        exclude = ["prop"]


class VideoUrlSerializer(MediaSerializer):

    url = StorageUrlField()

    class Meta:
        model = models.Video
        exclude = ["prop"]
        list_serializer_class = MediaListSerializer


class FeatureSerializer(ModelSerializer):

    serializer_choice_field = fields.ChoicesField

    class Meta:
        model = models.Feature
        exclude = ("override", "display", "organization")

    def to_representation(self, instance):
        name = instance.name
        if instance.display and instance.override:
            name = instance.override
        ret = super().to_representation(instance)
        ret["name"] = name
        return ret


class ImageOrderSerializer(common_ser.OrderSerializer):
    class Meta:
        model = models.Image


class LocationSerializer(ModelSerializer):
    serializer_choice_field = fields.ChoicesField

    class Meta:
        model = models.Location
        fields = (
            "continent",
            "country",
            "country_code",
            "region",
            "state",
            "city",
            "address",
            "apartment",
            "postal_code",
            "longitude",
            "latitude",
        )


class VideoOrderSerializer(common_ser.OrderSerializer):
    class Meta:
        model = models.Video


class PointOfInterestSerializer(ModelSerializer):

    coordinates = CoordinatesSerializer()
    image = URLField(required=False)

    def create(self, validated_data):
        coordinates = validated_data.pop("coordinates", None)
        category = validated_data.pop("category", None)
        instance = models.PointOfInterest.objects.create(**validated_data)

        if coordinates:
            instance.coordinates = models.Coordinates.objects.create(**coordinates)
            instance.save()

        if category:
            instance.category = YelpCategories.get_parent_category(category)
            instance.save()

        return instance

    def update(self, instance, validated_data):
        coordinates = validated_data.pop("coordinates", None)
        category = validated_data.pop("category", None)

        if coordinates:
            obj, _ = models.Coordinates.objects.update_or_create(
                pk=instance.coordinates_id, defaults=coordinates
            )
            instance.coordinates = obj

        if category:
            instance.category = YelpCategories.get_parent_category(category)
            instance.save()

        return super().update(instance, validated_data)

    class Meta:
        model = models.PointOfInterest
        exclude = ["prop"]


class PropertyMinimalSerializer(ModelSerializer):

    serializer_choice_field = fields.ChoicesField

    full_address = CharField(read_only=True)
    # cover_image = ReadOnlyField()
    # thumbnail = ReadOnlyField()
    # location = LocationSerializer(required=False, allow_null=True)

    class Meta:
        model = models.Property
        fields = (
            "id",
            "name",
            "full_address",
            "status",
            # "cover_image",
            # "thumbnail",
            # "location",
            "max_guests",
        )

    def __init__(self, *args, **kwargs):
        extra_required = kwargs.pop("extra_required", tuple())
        if not hasattr(self.Meta, "extra_kwargs"):
            self.Meta.extra_kwargs = {}
        self.Meta.extra_kwargs.update({field: {"required": True} for field in extra_required})
        super().__init__(*args, **kwargs)

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        property_changed.send(sender=models.Property, instance=instance)
        return instance


class PropertyListSerializer(PropertyMinimalSerializer):

    owner = OwnerForPropertyListSerializer(required=False, allow_null=True)
    # location = LocationSerializer(required=False, allow_null=True)
    is_from_api = SerializerMethodField()
    channels = SerializerMethodField()

    class Meta:
        model = models.Property
        fields = (
            "id",
            "name",
            "full_address",
            "rental_type",
            "property_type",
            "bathrooms",
            "bedrooms",
            "rental_type",
            "owner",
            "status",
            "cover_image",
            # "thumbnail",
            # "location",
            # "date_created",
            # "date_updated",
            "is_from_api",
            "channel_network_enabled",
            "channels",
        )

    # def get_cover_image(self, instance):
    #     """
    #     Removed cover_image @property in Property model in order to sandwich the image calls
    #     for cover_image into one query. This function requires that the queryset returns an
    #     annotation for the first_image
    #     """
    #     image_url = instance.first_image
    #     return StorageBackend().url(image_url) if image_url else None
    #
    # def get_thumbnail(self, instance):
    #     """
    #     Removed cover_image @property in Property model in order to sandwich the image calls
    #     for thumbnail into one query. This function requires that the queryset returns an
    #     annotation for the first_thumbnail
    #     """
    #     image_url = instance.first_thumbnail
    #     return StorageBackend().url(image_url) if image_url else None

    def get_is_from_api(self, instance) -> bool:
        return bool(instance.rental_connection_id)

    def get_channels(self, obj):
        channels = dict()
        try:
            channels["airbnb"] = ChannelSyncBasicSerializer(
                instance=AirbnbSync.objects.get(Q(prop=obj))
            ).data
        except AirbnbSync.DoesNotExist:
            pass
        # try:
        #     channels.append(
        #         ChannelSyncBasicSerializer(instance=TripAdvisorSync.objects.get(Q(prop=obj))).data)
        # except TripAdvisorSync.DoesNotExist:
        #     pass
        return channels


class AvailabilitySerializer(TimeFrameSerializerMixin):
    class Meta:
        model = models.Availability
        exclude = ["prop"]
        list_serializer_class = common_ser.CustomListSerializer


class RateSerializer(TimeFrameSerializerMixin):
    class Meta:
        model = models.Rate
        fields = "__all__"

    def get_queryset(self, validated_data):
        qs = super().get_queryset(validated_data)
        return qs.filter(seasonal=False)


class NestedRateSerializer(RateSerializer):
    class Meta:
        model = models.Rate
        exclude = ["prop"]
        list_serializer_class = common_ser.CustomListSerializer


class ReservationCalSerializer(ModelSerializer):

    guest = GuestMinimalSerializer()
    dynamic_status = ReadOnlyField()
    nightly_price = DecimalField(read_only=True, max_digits=12, decimal_places=2)

    class Meta:
        model = models.Reservation
        fields = (
            "id",
            "guest",
            "dynamic_status",
            "payment_template",
            "payment_custom_date",
            "start_date",
            "end_date",
            "status",
            "currency",
            "paid",
            "guests_adults",
            "guests_infants",
            "guests_children",
            "pets",
            "rebook_allowed_if_cancelled",
            "connection_id",
            "confirmation_code",
            "expiration",
            "refund_deposit_after",
            "cancellation_policy",
            "source",
            "date_updated",
            "date_created",
            "price",
            "nightly_price",
            "base_total",
            "nights",
        )


class ReservationFeeSerializer(ValueFormattedSerializer):
    class Meta:
        model = models.ReservationFee
        fields = (
            "type",
            "custom",
            "name",
            "value",
            "optional",
            "taxable",
            "refundable",
            "description",
        )
        extra_kwargs = {"type": {"source": "fee_tax_type", "default": empty}}


class ReservationFeeViewSerializer(ValueFormattedSerializer):
    custom = ReadOnlyField()

    class Meta:
        model = models.ReservationFee
        fields = ("id", "type", "custom", "name", "value", "optional", "taxable", "refundable")
        extra_kwargs = {"type": {"source": "fee_tax_type", "read_only": True}}

    def create(self, validated_data):
        validated_data.update({"custom": True})
        return super().create(validated_data)


class ReservationRateSerializer(ValueFormattedSerializer):
    nightly = CharField(read_only=True)

    class Meta:
        model = models.ReservationRate
        exclude = ["id", "reservation"]


class ReservationDiscountSerializer(ValueFormattedSerializer):
    class Meta:
        model = models.ReservationDiscount
        exclude = ["id", "reservation"]


class ReservationRefundSerializer(ValueFormattedSerializer):
    class Meta:
        model = models.ReservationRefund
        exclude = ["id", "reservation", "date_created", "date_updated"]


class ReservationPaymentSerializer(ModelSerializer):
    class Meta:
        model = Charge
        fields = ("external_id", "amount", "is_refundable", "refunded_amount")


class ReservationSerializer(ModelSerializer):

    prop = fields.NestedRelatedField(
        queryset=models.Property.objects.all(), serializer=PropertyMinimalSerializer, required=True
    )
    guest = fields.NestedRelatedField(
        queryset=Contact.objects.all(), serializer=GuestSerializer, allow_null=True, required=False
    )
    conversation = fields.NestedRelatedField(
        queryset=Conversation.objects.all(),
        serializer=ConversationSerializer,
        allow_null=True,
        required=False,
    )
    nightly_price = DecimalField(read_only=True, max_digits=12, decimal_places=2)
    price = DecimalField(read_only=True, max_digits=12, decimal_places=2)
    price_total = DecimalField(read_only=True, max_digits=12, decimal_places=2, source="price")
    fees = ReservationFeeSerializer(
        many=True, source="reservationfee_set", required=False, allow_null=True
    )
    discounts = ReservationDiscountSerializer(
        many=True, source="reservationdiscount_set", required=False, allow_null=True
    )
    refunds = ReservationRefundSerializer(many=True, required=False, allow_null=True)
    payments = ReservationPaymentSerializer(many=True, read_only=True)
    send_email = BooleanField(write_only=True, required=False, default=False)
    active_cancellation_policy = ReadOnlyField()
    dynamic_status = ReadOnlyField()
    listing_url = CharField(
        read_only=True, default="https://example.com/unique-listing-url"
    )  # FIXME Fake value
    price_formatted = CharField(read_only=True)
    organization = HiddenField(default=fields.DefaultOrganization())
    request_user = HiddenField(default=fields.RequestUser())
    currency = ReadOnlyField()
    serializer_choice_field = fields.ChoicesField

    class Meta:
        model = models.Reservation
        fields = (
            "id",
            "prop",
            "guest",
            "fees",
            "discounts",
            "payments",
            "active_cancellation_policy",
            "dynamic_status",
            "payment_schedule",
            "payment_template",
            "payment_custom_date",
            "start_date",
            "end_date",
            "status",
            "currency",
            "paid",
            "guests_adults",
            "guests_infants",
            "guests_children",
            "pets",
            "rebook_allowed_if_cancelled",
            "connection_id",
            "confirmation_code",
            "expiration",
            "refund_deposit_after",
            "cancellation_policy",
            "source",
            "send_email",
            "date_updated",
            "date_created",
            "listing_url",
            "price_formatted",
            "organization",
            "request_user",
            "conversation",
            "external_reservation",
            "price",
            "nightly_price",
            "base_total",
            "price_total",
            "nights",
            "cancellation_reason",
            "cancellation_notes",
            "refunds",
        )
        extra_kwargs = {
            "price": {"required": False, "allow_null": True},
            "guests_adults": {"default": 1},
            "guests_children": {"default": 0},
            "guests_infants": {"default": 0},
            "external_reservation": {"read_only": True},
        }
        depth = 1

    def __init__(self, instance=None, data=empty, skip_ipa_validation=False, **kwargs):
        self.skip_ipa_validation = skip_ipa_validation
        super().__init__(instance=instance, data=data, **kwargs)
        if (
            data is not empty
            and isinstance(self.fields["guest"], fields.NestedRelatedField)
            and isinstance(data, dict)
            and isinstance(data.get("guest"), dict)
        ):
            self.fields["guest"] = GuestSerializer(
                required=False, allow_null=True, data=data["guest"]
            )

    def _get_price(self, data):  # FIXME Use rates, fees, discounts send from ui
        kwargs = data.copy()
        kwargs.pop("guest", None)
        kwargs.pop("listing_url", None)
        kwargs.pop("calculate_price", None)
        kwargs.pop("send_email", None)
        kwargs.pop("organization", None)
        kwargs.pop("reservationfee_set", None)
        prop = kwargs.pop("prop", getattr(self.instance, "prop_id", None))
        if isinstance(prop, models.Property):
            kwargs["prop"] = prop
        else:
            kwargs["prop_id"] = prop

        tmp_reservation = models.Reservation(**kwargs)
        try:
            tmp_reservation.calculate_price(commit=False)
        except ValueError as e:
            no_rate = models.Rate.errors["no_rate"].format("")
            if "".join(e.args).startswith(no_rate):
                raise ValidationError("Not available")
            raise ValidationError(e.args)
        return tmp_reservation.price

    def _get_or_create_guest(self, guest_data, organization):
        if guest_data:
            guest_emails = list({guest_data.get("email"), guest_data.get("secondary_email")})
            guest = Contact.objects.filter(
                Q(organization=organization)
                & (Q(email__in=guest_emails) | Q(secondary_email__in=guest_emails))
            ).first()
            if guest:
                return guest
        guest_data["organization"] = organization
        field = self.fields["guest"]
        if isinstance(field, fields.NestedRelatedField):
            serializer = field.serializer()
        else:
            serializer = field
        return serializer.create(guest_data)

    def _validate_dates(self, start_date, end_date, status):

        if start_date and end_date and start_date > end_date:
            raise ValidationError("End of reservation must occur after start")

    def _validate_ipa(self, start_date, end_date, prop):
        if isinstance(prop, int):
            prop = models.Property.objects.get(pk=prop)
        if self.instance:
            reservations_excluded = [self.instance]
        else:
            reservations_excluded = []
        ipa = IsPropertyAvailable(
            prop,
            start_date,
            end_date,
            should_sync=True,
            reservations_excluded=reservations_excluded,
        )
        ipa.run_check()

        if not ipa.is_available():
            raise ValidationError(
                "Reservation is not available in the given period: {}".format(ipa.conflicts)
            )

    def validate_expiration(self, expiration):
        if expiration is not None and timezone.now() > expiration:
            raise ValidationError("Expiration must be a future date")
        return expiration

    def validate(self, data):
        def get_data(key):
            return data.get(key, getattr(self.instance, key, None))

        status = get_data("status")

        statuses = self.Meta.model.Statuses
        # Skip validation for Cancelled and Declined status
        if status in (statuses.Cancelled, statuses.Declined):
            self.skip_ipa_validation = True

        start_date = get_data("start_date")
        end_date = get_data("end_date")

        prop = get_data("prop")
        if prop.organization != self.context["organization"]:
            raise ValidationError({"prop": "Does not exist"})
        self._validate_dates(start_date, end_date, status)
        if not self.skip_ipa_validation:  # TODO Can we do better?
            self._validate_ipa(start_date, end_date, prop)

        if self.instance and status == statuses.Accepted:
            if ("expiration" not in data) and self.instance.is_inquiry_expired:
                raise ValidationError(
                    {"expiration": f"Reservation has expired on {self.instance.expiration}"}
                )

        non_price_safe = (
            "start_date",
            "end_date",
            "guests_adults",
            "guests_children",
            "guests_infants",
            "reservationrate",
            "reservationfee_set",
            "reservationdiscount_set",
            "refunds",
        )
        if data.get("price", None) is None and not data.keys().isdisjoint(non_price_safe):
            data["calculate_price"] = True

        return data

    def update(self, instance, validated_data):
        instance.snapshot_data()
        calculate_price = validated_data.pop("calculate_price", False)
        fees = validated_data.pop("reservationfee_set", None)
        discounts = validated_data.pop("reservationdiscount_set", None)
        guest_data = validated_data.pop("guest", None)
        refunds = validated_data.pop("refunds", None)
        context = self.context.get("request")
        if context:
            instance.request_user = context.user

        # Create notes if cancellation is detected
        status = validated_data.get("status", None)
        reason = validated_data.get("cancellation_reason", None)
        notes = validated_data.get("cancellation_notes", None)

        if (
            status
            and instance.status != status
            and status == ReservationStatuses.Cancelled.value
            and reason
        ):
            note_serializer = ReservationNoteCancellationSerializer(
                data={"reason": reason, "notes": notes},
                context={"reservation": instance, "user": context.user},
            )
            note_serializer.is_valid()
            note_serializer.save()

        instance = super().update(instance, validated_data)

        if fees is not None:
            instance._create_fees(fees)
        if discounts is not None:
            instance._create_discounts(discounts)
        if refunds is not None:
            instance._create_refunds(refunds)

        if guest_data is not None:
            Contact.objects.filter(pk=instance.guest.id).update(**guest_data)

        if calculate_price:
            validated_data.update(
                {
                    "start_date": instance.start_date,
                    "end_date": instance.end_date,
                    "guests_adults": instance.guests_adults,
                    "guests_children": instance.guests_children,
                    "guests_infants": instance.guests_infants,
                }
            )
            instance.recalculate_price()
        return instance

    def create(self, validated_data):
        validated_data.pop("listing_url", None)
        guest_data = validated_data.pop("guest", {})
        calculate_price = validated_data.pop("calculate_price", False)
        fees = validated_data.pop("reservationfee_set", None)
        discounts = validated_data.pop("reservationdiscount_set", None)

        # XXX COZ-557 Remove after front end adapts
        guest = self._get_or_create_guest(guest_data, validated_data["organization"])
        validated_data["guest_id"] = guest.pk  # TODO fix this damn hack
        validated_data.pop("organization", None)

        validated_data.update({"price": 0})
        instance = super().create(validated_data)
        Conversation.objects.create(reservation=instance)

        if not validated_data.get("base_total"):
            instance._calculate_base_total()
        instance._create_fees(fees)
        instance._create_discounts(discounts)

        # TODO need a better way of snapshotting data instead of putting it before
        instance.snapshot_data()
        if calculate_price:
            instance.calculate_price(commit=True)

        return instance


class InquirySerializer(ModelSerializer):
    hold = NullBooleanField(write_only=True, required=False)
    payment_requested = BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = models.Reservation
        fields = ("expiration", "payment_requested", "hold")

    def to_internal_value(self, data):
        ret = super().to_internal_value(data)
        hold = ret.pop("hold")

        if hold:
            ret["status"] = self.Meta.model.Statuses.Inquiry_Blocked
        else:
            ret["status"] = self.Meta.model.Statuses.Inquiry
        ret["send_email"] = True
        return ret


class RoomSerializer(ModelSerializer):

    serializer_choice_field = fields.ChoicesField

    features = FeatureSerializer(many=True, allow_null=True, required=False)

    class Meta:
        model = models.Room
        fields = ("id", "type", "beds", "features", "description", "bathrooms")
        extra_kwargs = {
            "bathrooms": {"allow_null": True},
            "type": {"source": "room_type", "allow_null": True},
            "beds": {"allow_null": True},
        }

    def validate(self, data):
        return {k: v for k, v in data.items() if v is not None}

    def create(self, validated_data):
        features = validated_data.pop("features", [])

        instance = self.Meta.model.objects.create(**validated_data)

        if features:
            instance.features.add(
                *models.Feature.objects.bulk_create(models.Feature(**data) for data in features)
            )
            instance.save()

        return instance

    def update(self, instance, validated_data):
        features = validated_data.pop("features", [])

        if features:
            if self.partial:
                raise ValidationError("Updating amenities is not supported yet")
            instance.features.all().delete()
            instance.features.add(
                *models.Feature.objects.bulk_create(models.Feature(**data) for data in features)
            )

        return super().update(instance, validated_data)


class SuitabilitySerializer(ModelSerializer):

    serializer_choice_field = fields.ChoicesField

    class Meta:
        model = models.Suitability
        exclude = ("id", "prop")


class TaxSerializer(FeeTaxSerializerMixin, ModelSerializer):
    class Meta:
        model = models.Tax
        fields = (
            "id",
            "name",
            "value",
            "type",
            "optional",
            "taxable",
            "refundable",
            "order",
            "calculation_method",
            "is_percentage",
            "prop",
        )
        extra_kwargs = {
            "type": {
                "source": "fee_tax_type",
                "choices": TaxTypes.choices(),
                "default": empty,
                "required": False,
            },
            "calculation_method": {"default": empty, "required": False},
            "prop": {"required": False},
        }


class PropertyUpdateSerializer(PropertyMinimalSerializer):

    owner = PrimaryKeyRelatedField(queryset=Owner.objects.all(), required=False, allow_null=True)
    basic_amenities = _model_serializer(models.BasicAmenities, exclude=["id", "prop"])(
        required=False
    )
    schedule_settings = _model_serializer(
        models.SchedulingAssistant, exclude=["id", "prop", "date_created"]
    )(required=False)
    suitability = SuitabilitySerializer(required=False)
    location = LocationSerializer(required=False, allow_null=True)
    arrival_instruction = _model_serializer(models.ArrivalInstruction)(
        required=False, allow_null=True
    )
    booking_settings = BookingSettingsSerializer(required=False, allow_null=True)
    pricing_settings = PricingSettingsSerializer(required=False, allow_null=True)
    availability_settings = AvailabilitySettingsSerializer(
        required=False, allow_null=True, partial=True
    )
    descriptions = ListingDescriptionSerializer(required=False, allow_null=True)
    availabilities = AvailabilitySerializer(many=True, source="availability_set", required=False)
    rates = NestedRateSerializer(many=True, source="rate_set", required=False)
    calendar = CalendarSerializer(source="cozmo_calendar", read_only=True)
    images = ImageUrlSerializer(many=True, source="image_set", read_only=True)
    videos = VideoUrlSerializer(many=True, source="video_set", read_only=True)
    rental_connection = PrimaryKeyRelatedField(read_only=True)
    group = PrimaryKeyRelatedField(
        queryset=models.Group.objects.all(), required=False, allow_null=True
    )
    source = SerializerMethodField()
    features = FeatureSerializer(many=True, required=False)

    rooms = RoomSerializer(many=True, source="room_set", read_only=True)
    pois = PointOfInterestSerializer(many=True, source="poi_set", read_only=True)
    fees = FeeSerializer(many=True, read_only=True, source="additionalfee_set.fees")
    taxes = TaxSerializer(many=True, read_only=True, source="additionalfee_set.taxes")
    discounts = DiscountSerializer(many=True, source="discount_set", read_only=True)
    payment_methods = _model_serializer(models.PaymentMethod)(many=True, read_only=True)
    organization = HiddenField(default=fields.DefaultOrganization())
    channels = SerializerMethodField()
    # channels = ChannelSyncSerializer(many=True, read_only=True)
    external_listings = PropertyExternalListingSerializer(many=True, read_only=True)
    request_user = HiddenField(default=fields.RequestUser())

    def get_channels(self, obj):
        channels = dict()
        try:
            channels["airbnb"] = ChannelSyncBasicSerializer(
                instance=AirbnbSync.objects.get(Q(prop=obj))
            ).data
            # from rental_integrations.airbnb.serializers import AirbnbListingSerializer, \
            #     ListingSerializer
            # airbnb_listing = AirbnbListingSerializer(obj).data
            # serializer = ListingSerializer(data=airbnb_listing)
            # if not serializer.is_valid():
            #     channels["airbnb"]["improvements"] = serializer.errors.keys()
        except AirbnbSync.DoesNotExist:
            pass
        # try:
        #     channels.append(
        #         ChannelSyncBasicSerializer(instance=TripAdvisorSync.objects.get(Q(prop=obj))).data)
        # except TripAdvisorSync.DoesNotExist:
        #     pass
        return channels

    def get_source(self, obj):
        try:
            source = obj.rental_connection.Types(obj.rental_connection.api_type).pretty_name
        except AttributeError:
            source = None
        return source

    class Meta:
        model = models.Property
        depth = 1
        fields = (
            "id",
            "name",
            "descriptions",
            "status",
            "cover_image",
            # "thumbnail",
            "owner",
            "schedule_settings",
            "suitability",
            "location",
            "arrival_instruction",
            "max_guests",
            "rates",
            "calendar",
            "rental_connection",
            "channels",
            "group",
            "source",
            "features",
            "fees",
            "taxes",
            "discounts",
            "rooms",
            "payment_methods",
            "payment_schedule",
            "payment_template",
            "payment_custom_date",
            "floor",
            "full_address",
            "time_zone",
            "license_number",
            "property_type",
            "rental_type",
            "bedrooms",
            "bathrooms",
            "building",
            "organization",
            "availabilities",
            "inventory_count",
            "booking_settings",
            "pricing_settings",
            "availability_settings",
            "images",
            "videos",
            "basic_amenities",
            "pois",
            "sync_logs",
            "max_guests",
            "locale",
            "channel_network_enabled",
            "size",
            "request_user",
            "external_listings",
        )
        read_only_fields = ("organization", "external_id")
        extra_kwargs = {"rental_type": {"required": True}}

    def validate_group(self, group):
        if "organization" in self.context:
            organization_id = self.context["organization"]
        else:
            organization_id = self.context["request"].user.organization.id

        if group is not None and (
            group.organization_id is None or group.organization_id != organization_id
        ):
            raise ValidationError("Choose assignee from your organization")
        return group

    def validate_owner(self, owner):
        if "organization" in self.context:
            organization_id = self.context["organization"]
        else:
            organization_id = self.context["request"].user.organization.id

        if owner is not None and (
            owner.organization_id is None or owner.organization_id != organization_id
        ):
            raise ValidationError("Choose owner from your organization")
        return owner

    def validate_pricing_settings(self, pricing_settings):
        if (
            pricing_settings is not None
            and self.instance
            and not hasattr(self.instance, "pricing_settings")
        ):
            serializer = type(self.fields["pricing_settings"])(data=pricing_settings)
            serializer.is_valid(raise_exception=True)
        return pricing_settings

    def _set_amenities_from_features(self, features, prop):

        basic_amenities = prop.basic_amenities
        suitability = prop.suitability

        for feature in features:
            name = feature.lower()
            if name in features_syn_rev.keys():
                setattr(basic_amenities, features_syn_rev[name], True)
            elif name in suitability_rev.keys():
                setattr(
                    suitability, suitability_rev[name], Suitability.SuitabilityProvided.Yes.value
                )

        basic_amenities.save()
        suitability.save()

    def _create_features(self, features, prop):
        features_map = {}
        features_to_add = []

        rental_connection = prop.rental_connection
        if rental_connection:
            features_map = rental_connection.service.features_map
        for feature in features:
            feature_name = titlecase(feature.get("name"))
            mapped_name = features_map.get(feature_name) or feature_name

            feature_queryset = models.Feature.objects.filter(
                Q(name__iexact=mapped_name)
                & (Q(organization=None) | Q(organization=prop.organization))
            )

            if feature_queryset:
                features_to_add.append(feature_queryset.first())
            else:
                feature["name"] = mapped_name
                feature_serializer = FeatureSerializer(data=feature)
                if feature_serializer.is_valid():
                    features_to_add.append(feature_serializer.save(organization=prop.organization))

        prop.features.clear()
        prop.features.add(*features_to_add)
        if rental_connection:
            rental_connection.features.add(*features_to_add)
            rental_connection.save()

    def validate(self, data):
        if "rental_type" in data and "property_type" in data:
            rental_type = data["rental_type"]
            property_type = data["property_type"]

            for valid_rental_types in (
                {"rentals": (Rentals.Entire_Home,), "types": (PropertyTypes.Campsite,)},
                {
                    "rentals": (Rentals.Private, Rentals.Shared),
                    "types": (
                        PropertyTypes.Aparthotel,
                        PropertyTypes.Bed_and_Breakfast,
                        PropertyTypes.Boutique_Hotel,
                        PropertyTypes.Heritage_Hotel,
                        PropertyTypes.Hostel,
                        PropertyTypes.Hotel,
                        PropertyTypes.Lodge,
                        PropertyTypes.Resort,
                        PropertyTypes.Ryokan,
                    ),
                },
            ):
                property_types = valid_rental_types["types"]
                rental_types = valid_rental_types["rentals"]
                if property_type in property_types and rental_type not in rental_types:
                    raise ValidationError(
                        "property_type '{}' must be of rental_type '{}'".format(
                            property_type, ", ".join(rt.pretty_name for rt in rental_types)
                        )
                    )

        return super().validate(data)

    def update(self, instance, validated_data):
        instance.snapshot_data()

        validated_data.pop("additionalfee_set", [])
        validated_data.pop("room_set", [])
        validated_data.pop("poi_set", [])

        booking_settings_name = "booking_settings"
        booking_settings = validated_data.pop(booking_settings_name, None)
        if booking_settings:
            check_in_out = booking_settings.pop("check_in_out", None)
            bs, _ = models.BookingSettings.objects.update_or_create(
                prop=instance, defaults=booking_settings
            )
            if check_in_out:
                models.CheckInOut.objects.update_or_create(
                    booking_settings=bs, defaults=check_in_out
                )
            setattr(instance, booking_settings_name, bs)

        for field in (
            "basic_amenities",
            "schedule_settings",
            "suitability",
            "descriptions",
            "pricing_settings",
            "availability_settings",
            "long_term_rental_settings",
        ):
            value = validated_data.pop(field, None)
            if value:
                model_class = self.fields[field].Meta.model
                obj, _ = model_class.objects.update_or_create(prop=instance, defaults=value)
                setattr(instance, field, obj)

        for field in ("location", "arrival_instruction"):
            value = validated_data.pop(field, None)
            if value:
                model_class = self.fields[field].Meta.model
                obj, _ = model_class.objects.update_or_create(
                    id=getattr(instance, f"{field}_id"), defaults=value
                )
                setattr(instance, field, obj)

        features = validated_data.pop("features", None)
        if features is not None:
            self._create_features(features, instance)
            self._set_amenities_from_features(features, instance)

        self.fields["rates"].create(validated_data.pop("rate_set", []), prop=instance)
        self.fields["availabilities"].create(
            validated_data.pop("availability_set", []), prop=instance
        )

        context = self.context.get("request")
        if context:
            instance.request_user = context.user

        is_property_activating = (
            validated_data.get("status", None) == PropertyStatuses.Active.value
            and instance.status != PropertyStatuses.Active.value
        )
        updated_instance = super().update(instance, validated_data)

        if is_property_activating:
            property_activated.send(sender=updated_instance.__class__, instance=updated_instance)

        return updated_instance


class PropertyCreateSerializer(PropertyUpdateSerializer):

    rooms = RoomSerializer(many=True, source="room_set", required=False)
    pois = PointOfInterestSerializer(many=True, source="poi_set", required=False)
    fees = FeeSerializer(many=True, source="additionalfee_set.fees", required=False)
    taxes = TaxSerializer(many=True, source="additionalfee_set.taxes", required=False)
    discounts = DiscountSerializer(many=True, required=False, source="discount_set")
    payment_methods = _model_serializer(models.PaymentMethod)(many=True, required=False)

    images = ImageUrlSerializer(many=True, source="image_set", required=False)
    videos = VideoUrlSerializer(many=True, source="video_set", required=False)

    class Meta(PropertyUpdateSerializer.Meta):
        read_only_fields = None
        extra_kwargs = {"property_type": {"required": False}}

    def _add_fees(self, prop, fees) -> list:
        a_fees = {}
        if fees:
            a_fees = models.AdditionalFee.objects.bulk_create(
                models.AdditionalFee(prop=prop, **data) for data in fees
            )
        elif prop.rental_connection:
            a_fees = models.AdditionalFee.create_default_fees(prop)
        return a_fees

    def create(self, validated_data):
        rates = validated_data.pop("rate_set", [])
        fees_taxes = validated_data.pop("additionalfee_set", {})
        fees = fees_taxes.pop("fees", [])
        taxes = fees_taxes.pop("taxes", [])
        discounts = validated_data.pop("discount_set", [])
        images = validated_data.pop("image_set", [])
        videos = validated_data.pop("video_set", [])
        rooms = validated_data.pop("room_set", [])
        pois = validated_data.pop("poi_set", [])

        owner = validated_data.pop("owner", None)
        b_amenities = validated_data.pop("basic_amenities", {})
        s_assistant = validated_data.pop("schedule_settings", {})
        suitability = validated_data.pop("suitability", {})
        location = validated_data.pop("location", None)
        arrival_instr = validated_data.pop("arrival_instruction", None)
        pricing_settings = validated_data.pop("pricing_settings", None)
        long_term_rental_settings = validated_data.pop("long_term_rental_settings", dict())
        booking_settings = validated_data.pop("booking_settings", dict())
        check_in_out = booking_settings.pop("check_in_out", dict())
        availabilities = validated_data.pop("availability_set", [])
        availability_settings = validated_data.pop("availability_settings", dict())
        descriptions = validated_data.pop("descriptions", None)

        payment_methods = validated_data.pop("payment_methods", [])
        features = validated_data.pop("features", [])

        prop = super().create(validated_data)

        if features:
            self._create_features(features, prop)
            self._set_amenities_from_features(features, prop)

        prop.payment_methods.add(
            *models.PaymentMethod.objects.bulk_create(
                models.PaymentMethod(**data) for data in payment_methods
            )
        )

        self._add_fees(prop, fees + taxes)
        self.fields["availabilities"].create(availabilities, prop=prop)
        self.fields["rates"].create(rates, prop=prop)
        self.fields["images"].create(images, prop=prop)
        self.fields["videos"].create(videos, prop=prop)
        prop.discount_set.bulk_create(models.Discount(prop=prop, **data) for data in discounts)
        prop.room_set.bulk_create(models.Room(prop=prop, **data) for data in rooms)

        pois_coords_ids = models.Coordinates.objects.bulk_create(
            models.Coordinates(**data.pop("coordinates")) for data in pois
        )
        prop.poi_set.bulk_create(
            models.PointOfInterest(prop=prop, coordinates=coord, **data)
            for data, coord in zip(pois, pois_coords_ids)
        )

        models.BasicAmenities.objects.update_or_create(prop=prop, defaults=b_amenities)
        models.SchedulingAssistant.objects.update_or_create(prop=prop, defaults=s_assistant)
        models.Suitability.objects.update_or_create(prop=prop, defaults=suitability)
        bs, _ = models.BookingSettings.objects.update_or_create(
            prop=prop, defaults=booking_settings
        )
        ltrs, _ = LongTermRentalSettings.objects.update_or_create(
            prop=prop, defaults=long_term_rental_settings
        )
        models.CheckInOut.objects.update_or_create(booking_settings=bs, defaults=check_in_out)
        if owner:
            prop.owner = OwnerUser.objects.create(**owner)
        if location:
            prop.location = models.Location.objects.create(**location)
        if arrival_instr:
            prop.arrival_instruction = models.ArrivalInstruction.objects.create(**arrival_instr)
        if pricing_settings:
            models.PricingSettings.objects.create(prop=prop, **pricing_settings)
        # if booking_settings:
        #     booking_settings["prop"] = prop
        #     bs = self.fields["booking_settings"].create(booking_settings)
        #     check_in_out = booking_settings.pop("check_in_out", dict())
        #     check_in_out["booking_settings"] = bs
        #     models.CheckInOut.objects.create(**check_in_out)
        availability_settings["prop"] = prop
        self.fields["availability_settings"].create(availability_settings)
        if descriptions:
            descriptions["prop"] = prop
            self.fields["descriptions"].create(descriptions)

        channel_network_settings = validated_data.pop("channel_network_enabled", None)
        if not channel_network_settings and prop.organization.settings.channel_network_enabled:
            prop.channel_network_enabled = True

        prop.save()

        return prop


class PropertySerializer(PropertyCreateSerializer):

    images = ImageSerializer(many=True, source="image_set", required=False)
    videos = VideoSerializer(many=True, source="video_set", required=False)
    owner = OwnerSerializer(required=False, allow_null=True)


class PropertyCalMinSerializer(PropertyMinimalSerializer):
    blockings = BlockingSerializer(many=True, source="blocking_included")
    ical_events = SerializerMethodField()

    class Meta:
        model = models.Property
        fields = (
            "id",
            "name",
            "full_address",
            "cover_image",
            "blockings",
            "ical_events",
            "bedrooms",
            "bathrooms",
            "max_guests",
        )

    def get_ical_events(self, instance):
        fr = self.context["request"].query_params.get("from")
        to = self.context["request"].query_params.get("to")
        try:
            events = instance.cozmo_calendar.get_events(fr, to)
        except ObjectDoesNotExist:
            events = []
        return events


class PropertyCalSerializer(PropertyCalMinSerializer):

    reservations = ReservationCalSerializer(many=True, source="reservation_included")
    rates = RateSerializer(many=True, source="rate_included", read_only=True)
    base_rate = SerializerMethodField()

    class Meta:
        model = models.Property
        fields = PropertyCalMinSerializer.Meta.fields + ("reservations", "rates", "base_rate")

    def get_base_rate(self, instance):
        base_rate = {}

        if hasattr(instance, "pricing_settings"):
            base_rate["nightly"] = instance.pricing_settings.nightly
            base_rate["weekend"] = instance.pricing_settings.weekend
        else:
            base_rate.update({"nightly": None, "weekend": None})

        if hasattr(instance, "availability_settings"):
            base_rate["min_stay"] = instance.availability_settings.min_stay
        else:
            base_rate["min_stay"] = None

        return base_rate


class GroupSerializer(ModelSerializer):

    serializer_choice_field = fields.ChoicesField

    organization = HiddenField(default=fields.DefaultOrganization())
    properties_count = SerializerMethodField()

    class Meta:
        model = models.Group
        exclude = ["date_created", "external_id"]

        extra_kwargs = {"date_updated": {"read_only": True, "required": False}}

    def get_properties_count(self, obj):
        return obj.property_set.count()


class TurnDaySerializer(ModelSerializer):
    time_frame = DateRangeField()

    class Meta:
        model = models.TurnDay
        exclude = ["prop"]


class SchedulingAssistantSerializer(ModelSerializer):
    class Meta:
        model = models.SchedulingAssistant
        exclude = ("date_created", "date_updated", "id")


class SeasonalRateSerializer(TimeFrameSerializerMixin):
    seasonal = HiddenField(default=True)

    class Meta:
        model = models.Rate
        exclude = ("prop", "weekend", "weekly", "monthly", "extra_person_fee")

    def get_queryset(self, validated_data):
        qs = super().get_queryset(validated_data)
        return qs.filter(seasonal=True)


class ReservationNoteSerializer(ModelSerializer):
    author_name = CharField(source="author.username", read_only=True)
    author = HiddenField(default=fields.RequestUser())

    class Meta:
        model = models.ReservationNote
        exclude = ("reservation",)


class ReservationNoteCancellationSerializer(Serializer):
    reason = IntegerField()
    notes = CharField(allow_null=True, allow_blank=True, required=False)

    def create(self, validated_data):
        body = {CancellationReasons.renter.value: "The renter has cancelled this reservation"}.get(
            validated_data.pop("reason", None), "This reservation has been cancelled"
        )

        notes = validated_data.pop("notes")
        if notes:
            body = f"{body} - {notes}"

        instance = ReservationNote.objects.create(
            reservation=self.context["reservation"], author=self.context["user"], body=body
        )
        return instance


class ChargeSerializer(Serializer):
    discounts = DiscountSerializer(many=True)
    fees = FeeSerializer(many=True, prop_required=True)
    rates = RateSerializer(many=True)
    taxes = TaxSerializer(many=True, prop_required=True)
    prop = CharField()


class ReservationReportSerializer(ModelSerializer):
    guest_name = CharField(source="guest.full_name", read_only=True)
    property_name = CharField(source="prop.name", read_only=True)
    property_address = CharField(source="prop.full_address", read_only=True)
    status = CharField(source="dynamic_status")
    source = CharField(source="get_source_display")
    cancellation_reason = CharField(source="get_cancellation_reason_display")

    class Meta:
        model = models.Reservation
        fields = (
            "start_date",
            "end_date",
            "guest_name",
            "property_name",
            "property_address",
            "nights",
            "guests",
            "status",
            "currency",
            "base_total",
            "price",
            "source",
            "confirmation_code",
            "cancellation_reason",
            "cancellation_notes",
        )

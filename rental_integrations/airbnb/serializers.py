import json
import mimetypes
from base64 import b64encode
from contextlib import suppress
from datetime import timedelta
from logging import getLogger
from mimetypes import guess_type

from _decimal import Decimal
from django.db.models import CharField, ExpressionWrapper, F
from django.db.models.functions import Greatest, Least, Lower, Upper
from django.utils import timezone
from drf_extra_fields.fields import Base64ImageField
from rest_framework import serializers

from app_marketplace.choices import AirbnbSyncCategory
from cozmo_common.fields import ChoicesField, DefaultOrganization, OptionalCharField
from listings.calendars.models import ExternalCalendarEvent
from listings.choices import Currencies, ReservationStatuses
from listings.models import Fee, Property, Room, Suitability
from listings.serializers import (
    PropertyCreateSerializer,
    ReservationSerializer as CozmoReservationSerializer,
)
from rental_integrations.airbnb import choices, mappings, models
from rental_integrations.airbnb.choices import (
    Amenity,
    AmountType,
    CHECK_IN_FROM_TIME_CHOICES,
    CHECK_IN_TO_TIME_CHOICES,
    CancellationPolicy,
    CheckInOutTime,
    CountryCode,
    FeeType,
    ListingExpectation,
    MessageAttachmentType,
    MessageBusinessPurpose,
    MessageInquiryStatus,
    MessageReservationStatus,
    MessageRole,
    PhotoType,
    StatusCategory,
    SyncItem,
)
from rental_integrations.airbnb.constants import (
    MAX_PHOTOS,
    MIN_AMENITIES,
    MIN_DESCRIPTION,
    MIN_HD_PHOTOS,
    MIN_HD_PHOTOS_WIDTH_PX,
    MIN_PHOTOS,
)
from rental_integrations.airbnb.exceptions import (
    AdvancedNoticeInvalidValueValidationError,
    NoChildrenDetailsValidationError,
)
from rental_integrations.airbnb.utils import to_cozmo_reservation
from rental_integrations.choices import ListingApprovalStatus
from rental_integrations.exceptions import (
    ListingRequirementValidationError,
    MinAmenitiesValidationError,
    MinDescriptionValidationError,
    MinHDPhotoValidationError,
    MinPhotoValidationError,
    NoSTRLicenseValidationError,
)
from rental_integrations.serializers import BaseListingReviewSerializer
from .models import AirbnbAccount, AirbnbSync, Listing, Reservation
from .service import AirbnbService

logger = getLogger(__name__)


def save_reservation(prop, context, reservation):
    r = to_cozmo_reservation(reservation)
    r["prop"] = prop.id
    reservation_serializer = CozmoReservationSerializer(
        data=r, context=context, skip_ipa_validation=True
    )
    try:
        reservation_serializer.is_valid(raise_exception=True)
        r = reservation_serializer.save()
        reservation["reservation"] = r.id
        airbnb_reservation_serializer = ReservationSerializer(data=reservation)
        airbnb_reservation_serializer.is_valid(raise_exception=True)
        airbnb_reservation_serializer.save()
    except Exception as e:
        logger.warning("Could not save reservation for Airbnb %s, %s", prop.id, str(e))
        logger.warning("Reservation data: {}".format(str(reservation)))


def sync_reservations(service, prop, context):
    reservations = service.get_reservations(prop.airbnb_sync.get().external_id)
    for each in reservations:
        save_reservation(prop, context, each)


class PropertyIdSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(min_value=0))
    push_all = serializers.BooleanField(default=False, required=False)
    organization = serializers.HiddenField(default=DefaultOrganization())

    def validate(self, data):
        push_all = data.get("push_all", False)
        if not data["ids"] and not push_all:
            raise serializers.ValidationError({"ids": self.error_messages["required"]})

        properties_qs = (
            Property.objects.existing()
            .filter(organization=data["organization"])
            .only("id", "name")
            .prefetch_related("image_set", "location")
        )

        if not data.get("push_all", False):
            properties_qs = properties_qs.filter(id__in=data["ids"])

        data["ids"] = properties_qs
        return data

    def create(self, validated_data):
        to_sync = validated_data["ids"]
        to_sync.update(airbnb_sync_id=validated_data["app_id"])
        # TODO this hasn't been migrated to the new Airbnb listing code
        # ListingLegacy.objects.bulk_create(
        #     ListingLegacy(prop_id=prop.id, external_id="")
        #     for prop in to_sync.filter(airbnb_listing=None)
        # )
        return to_sync


class RoomInventorySerializer(serializers.Serializer):

    type = serializers.ChoiceField(choices=choices.BedType.choices())
    quantity = serializers.IntegerField(min_value=1)


class RoomInventoryAmenitiesSerializer(RoomInventorySerializer):

    type = serializers.ChoiceField(choices=choices.RoomAmenity.choices())


class ListingRoomSerializer(serializers.Serializer):
    listing_id = serializers.IntegerField(required=False)
    room_number = serializers.IntegerField(min_value=0)
    beds = serializers.ListField(
        allow_empty=True, allow_null=True, child=RoomInventorySerializer()
    )
    room_amenities = serializers.ListField(
        allow_empty=True, allow_null=True, child=RoomInventoryAmenitiesSerializer()
    )


class CheckInSerializer(serializers.Serializer):
    category = ChoicesField(choices=choices.Checkin)
    instruction = serializers.CharField()


class ListingDescription(serializers.Serializer):
    name = OptionalCharField()
    summary = OptionalCharField(max_length=500)
    space = OptionalCharField()
    access = OptionalCharField()
    interaction = OptionalCharField()
    notes = OptionalCharField()
    neighborhood_overview = OptionalCharField()
    transit = OptionalCharField()
    house_rules = OptionalCharField()
    description = OptionalCharField()


class ListingExpectationSerializer(serializers.Serializer):
    type = ChoicesField(choices=ListingExpectation.choices())
    added_details = serializers.CharField(max_length=150)


class GuestControlsSerializer(serializers.Serializer):

    allows_children_as_host = serializers.BooleanField(default=False)
    allows_infants_as_host = serializers.BooleanField(default=False)
    children_not_allowed_details = serializers.CharField(
        allow_null=True, allow_blank=True, required=False
    )
    allows_smoking_as_host = serializers.BooleanField(default=False)
    allows_pets_as_host = serializers.BooleanField(default=False)
    allows_events_as_host = serializers.BooleanField(default=False)

    def validate(self, data):
        # If you selected false for any of the kids allowed rules (infants or children),
        # children_not_allowed_details field is required to provide details about why
        # the place is not suitable for children.
        allows_children = data["allows_children_as_host"] or data["allows_infants_as_host"]
        if not allows_children and "children_not_allowed_details" not in data:
            raise NoChildrenDetailsValidationError()

        return data


class BookingSettingsSerializer(serializers.Serializer):
    cancellation_policy_category = ChoicesField(
        choices=choices.CancellationPolicy.choices(), allow_null=True, required=False
    )
    check_in_time_start = ChoicesField(
        choices=choices.CheckInOutTime.choices() + CHECK_IN_FROM_TIME_CHOICES,
        allow_null=True,
        required=False,
    )
    check_in_time_end = ChoicesField(
        choices=choices.CheckInOutTime.choices() + CHECK_IN_TO_TIME_CHOICES,
        allow_null=True,
        required=False,
    )
    check_out_time = serializers.IntegerField(
        min_value=0, max_value=23, allow_null=True, required=False
    )
    instant_booking_allowed_category = ChoicesField(
        choices=choices.InstantBookingAllowedCategories, required=False
    )
    instant_book_welcome_message = serializers.CharField(allow_blank=True, required=False)
    listing_expectations_for_guests = serializers.ListField(
        allow_empty=True, child=ListingExpectationSerializer(), required=False
    )
    guest_controls = GuestControlsSerializer(required=False)


class StandardFeeSerializer(serializers.Serializer):
    fee_type = ChoicesField(choices=FeeType.choices())
    amount_type = ChoicesField(choices=AmountType.choices())
    amount = serializers.IntegerField()


class PhotoSerializer(serializers.Serializer):
    # TODO Please note, there is a maximum of 200 photos for each listing.
    listing_id = serializers.IntegerField(required=False)
    content_type = ChoicesField(choices=PhotoType.choices())
    filename = serializers.CharField()
    image = Base64ImageField()
    caption = serializers.CharField(required=False, allow_blank=True)
    sort_order = serializers.IntegerField(required=False)

    def validate(self, data):
        errors = list()
        content_type, _ = guess_type(data["filename"])
        if content_type != data["content_type"]:
            errors.append(serializers.ValidationError("filename and content_type do not match"))

        if errors:
            raise serializers.ValidationError(errors)
        return data


class PricingSettingsSerializer(serializers.Serializer):

    # listing_id = serializers.IntegerField(required=False)
    listing_currency = ChoicesField(choices=Currencies.choices())
    default_daily_price = serializers.IntegerField(
        min_value=10, max_value=25000, allow_null=True, required=False
    )
    weekend_price = serializers.IntegerField(
        min_value=0, max_value=25000, required=False
    )  # TODO can be set to 0 to remove fee 10
    security_deposit = serializers.IntegerField(
        min_value=0, max_value=5000, required=False
    )  # TODO can be set to 0 to remove fee 100
    # TODO Maximum cleaning fee is (USD $600 + 25% nightly price).
    cleaning_fee = serializers.IntegerField(
        min_value=0, required=False
    )  # TODO can be set to 0 to remove fee 5
    guests_included = serializers.IntegerField(min_value=1, default=1, required=False)
    price_per_extra_person = serializers.IntegerField(
        min_value=0, required=False
    )  # TODO can be set to 0 to remove fee 5
    monthly_price_factor = serializers.DecimalField(
        min_value=0.0,
        max_value=1.0,
        max_digits=2,
        decimal_places=1,
        allow_null=True,
        required=False,
    )
    # TODO Must be greater than montly_price_factor
    weekly_price_factor = serializers.DecimalField(
        min_value=0.0,
        max_value=1.0,
        max_digits=2,
        decimal_places=1,
        allow_null=True,
        required=False,
    )
    standard_fees = StandardFeeSerializer(many=True, required=False)

    # def validate(self, data):
    # TODO validate that cleaning fee is not over 600 USD + 25% nightly price


class AdvancedNoticeSerializer(serializers.Serializer):
    # TODO Allowed values: 0-24, 48, 72, 168
    hours = serializers.IntegerField(default=48)
    # Do you allow reservation requests for bookings with shorter notice
    # * 0—prohibit requests, * 1—allow requests.
    allow_request_to_book = serializers.IntegerField(allow_null=True, required=False)

    def validate(self, data):
        errors = list()
        allowed_hours = [48, 72, 168] + [x for x in range(0, 25)]
        if data["hours"] not in allowed_hours:
            errors.append(AdvancedNoticeInvalidValueValidationError())

        if data["allow_request_to_book"] not in [0, 1]:
            errors.append(serializers.ValidationError("allow_request_to_book value is invalid"))

        if errors:
            raise serializers.ValidationError(errors)

        return data


class DistantRequestsSerializer(serializers.Serializer):
    # Number of days in the future that is allowed for reservations
    days = serializers.IntegerField(default=-1)

    def validate(self, data):
        allowed_values = [-1, 0, 90, 180, 365]
        if data["days"] not in allowed_values:
            raise serializers.ValidationError("Max days notice value is not valid")

        return data


class PreparationTimeSerializer(serializers.Serializer):
    days = serializers.IntegerField(min_value=0, max_value=2, default=0)


class DayOfWeekSerializer(serializers.Serializer):
    day_of_week = serializers.IntegerField(min_value=0, max_value=6)


class DayOfWeekMinNightSerializer(DayOfWeekSerializer):
    day_of_week = serializers.IntegerField(min_value=0, max_value=6)
    min_nights = serializers.IntegerField(min_value=0)


class AvailabilityRuleSerializer(serializers.Serializer):
    default_min_nights = serializers.IntegerField(min_value=0, required=False)
    default_max_nights = serializers.IntegerField(min_value=0, required=False)
    booking_lead_time = AdvancedNoticeSerializer(required=False)
    max_days_notice = DistantRequestsSerializer(required=False)
    seasonal_min_nights = serializers.ListField(allow_empty=True, required=False)  # TODO
    turnover_days = PreparationTimeSerializer(required=False)
    day_of_week_check_in = DayOfWeekSerializer(many=True, required=False)
    day_of_week_check_out = DayOfWeekSerializer(many=True, required=False)
    day_of_week_min_nights = DayOfWeekMinNightSerializer(many=True, required=False)  # TODO


class CalendarOperationsSerializer(serializers.Serializer):

    dates = serializers.ListField(
        child=serializers.CharField(), allow_null=True, required=False
    )  # TODO are the data ranges valid?
    daily_price = serializers.IntegerField(min_value=10, allow_null=True, required=False)  # TODO
    availability = serializers.ChoiceField(
        choices=choices.CalendarAvailabilityOptions.choices(), allow_null=True, required=False
    )
    available_count = serializers.IntegerField(allow_null=True, required=False)  # TODO
    min_nights = (serializers.IntegerField(allow_null=True, required=False),)  # TODO
    max_nights = (serializers.IntegerField(allow_null=True, required=False),)  # TODO
    closed_to_arrival = serializers.BooleanField(required=False)  # TODO
    closed_to_departure = serializers.BooleanField(required=False)  # TODO
    notes = serializers.CharField(allow_null=True, allow_blank=True, required=False)

    # def validate(self, data):
    # pass
    # TODO validate date ranges vs single date strings


class ExtrasSerializers(serializers.Serializer):

    photos = PhotoSerializer(many=True)
    listing_descriptions = ListingDescription()
    pricing_settings = PricingSettingsSerializer()
    booking_settings = BookingSettingsSerializer()
    listing_rooms = ListingRoomSerializer(many=True)
    availability_rules = AvailabilityRuleSerializer()
    calendar_operations = CalendarOperationsSerializer(many=True, required=False)

    def validate_photos(self, photos):
        if len(photos) > MAX_PHOTOS:
            raise serializers.ValidationError("Max photos")
        return photos


class ListingSerializer(serializers.Serializer):

    synchronization_category = ChoicesField(
        choices=choices.SynchronizationCategory,
        allow_null=True,
        default=choices.SynchronizationCategory.sync_undecided.pretty_name,
    )
    name = serializers.CharField(max_length=255, min_length=8)
    property_type_group = ChoicesField(choices=choices.PropertyTypeGroup.choices(), required=False)
    property_type_category = ChoicesField(choices=choices.PropertyType.choices(), required=False)
    room_type_category = ChoicesField(choices=choices.RoomType, required=False)
    bedrooms = serializers.IntegerField(min_value=0, max_value=50, required=False)
    bathrooms = serializers.DecimalField(
        min_value=0, max_value=50, decimal_places=1, max_digits=3, required=False
    )
    # TODO if one, bed_type_category must describe the type of room
    beds = serializers.IntegerField(required=False)
    amenity_categories = serializers.ListField(
        child=ChoicesField(choices=choices.Amenity.choices(), required=False), required=False
    )
    check_in_option = CheckInSerializer(required=False)
    requested_approval_status_category = ChoicesField(
        choices=choices.StatusCategory, default=choices.StatusCategory.new.value
    )
    has_availability = serializers.BooleanField(required=False)
    permit_or_tax_id = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    apt = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    street = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()  # should be Two letter abb
    zipcode = serializers.CharField()
    country_code = ChoicesField(choices=CountryCode.choices())
    lat = serializers.DecimalField(max_digits=15, decimal_places=6)
    lng = serializers.DecimalField(max_digits=15, decimal_places=6)
    directions = serializers.CharField(allow_blank=True, required=False)
    person_capacity = serializers.IntegerField(default=1)
    listing_currency = ChoicesField(choices=Currencies, required=False)
    listing_price = serializers.IntegerField(min_value=10, max_value=25000)

    # Airbnb ignores the four attributes below if property_type = entire_place
    bathroom_shared = serializers.BooleanField(required=False)
    bathroom_shared_with_category = serializers.ListField(
        child=ChoicesField(choices=choices.SharedCategory, required=False), required=False
    )
    common_spaces_shared = serializers.BooleanField(required=False)
    common_spaces_shared_with_category = serializers.ListField(
        child=ChoicesField(choices=choices.SharedCategory, required=False), required=False
    )

    # Two attrs below are required only for properties with room inventory only
    # Also must have property_type_category specified
    # and cannot be used with "house". TODO required if has room inventory
    total_inventory_count = serializers.IntegerField(min_value=0, required=False)
    property_external_id = serializers.CharField(required=False)
    extras = ExtrasSerializers(required=True)

    def validate_bathrooms(self, bathrooms):
        if int(bathrooms * 10) % 5 != 0:
            raise serializers.ValidationError("Granularity 0.5 is required")
        return bathrooms

    def _validate_regulations(self, data):
        # TODO
        country = data["country_code"].lower()
        city = data["city"].lower()
        state = data["state"]
        regulated_us_cities = ("santa monica", "chicago", "san francisco")
        regulated_es_cities = ("catalonia", "andalusia")
        has_us_city_regulations = country == "us" and city in regulated_us_cities
        has_ca_city_regulations = country == CountryCode.CA and city == "vancouver"
        has_es_city_regulations = country == CountryCode.ES and state in regulated_es_cities
        has_other_city_regulations = country in (CountryCode.FR, CountryCode.JP, CountryCode.PT)
        return not (
            not data["permit_or_tax_id"]
            and (
                has_us_city_regulations
                or has_other_city_regulations
                or has_ca_city_regulations
                or has_es_city_regulations
            )
        )

    def validate(self, data):
        listing_requirement_errors = dict()
        amenity_categories = data["amenity_categories"]
        if len(amenity_categories) < MIN_AMENITIES:
            listing_requirement_errors["AMENITIES"] = MinAmenitiesValidationError()

        extras = data["extras"]
        photos = extras["photos"]
        if len(photos) < MIN_PHOTOS:
            listing_requirement_errors["MIN_PHOTO"] = MinPhotoValidationError()

        high_res_count = sum(
            1
            for photo in photos
            if photo["image"].image.size >= (MIN_HD_PHOTOS_WIDTH_PX, MIN_HD_PHOTOS_WIDTH_PX)
        )
        if high_res_count < MIN_HD_PHOTOS:
            listing_requirement_errors["MIN_HD_PHOTO"] = MinHDPhotoValidationError()

        descriptions = extras["listing_descriptions"]
        all_descriptions = "".join(v for v in descriptions.values() if isinstance(v, str))
        if len(all_descriptions) < MIN_DESCRIPTION:
            listing_requirement_errors["DESCRIPTIONS"] = MinDescriptionValidationError()

        if not self._validate_regulations(data):
            listing_requirement_errors["STR_LICENSE"] = NoSTRLicenseValidationError()

        booking_settings = extras["booking_settings"]
        check_in_start = booking_settings["check_in_time_start"]
        check_in_end = booking_settings["check_in_time_end"]
        check_in_flexible = CheckInOutTime.flexible.value
        is_check_in_flexible = (
            check_in_start == check_in_flexible or check_in_end == check_in_flexible
        )

        if not is_check_in_flexible and (check_in_end - check_in_start) < 2:
            listing_requirement_errors["CHECK_IN_TIME_WINDOW"] = serializers.ValidationError(
                "Check in time window is not legal"
            )

        if listing_requirement_errors:
            raise ListingRequirementValidationError(listing_requirement_errors)
        return data


class BookingDetailsSerializer(serializers.Serializer):
    listing_id = serializers.IntegerField()
    reservation_confirmation_code = serializers.CharField(allow_null=True)


class AttachmentSerializer(serializers.Serializer):
    type = serializers.ChoiceField(
        choices=(
            ("Inquiry", ReservationStatuses.Inquiry),
            ("SpecialOffer", ReservationStatuses.Inquiry),
            ("Reservation", ReservationStatuses.Accepted),
        )
    )
    status = serializers.CharField()
    booking_details = BookingDetailsSerializer()


class AttachmentImageSerializer(serializers.Serializer):
    url = serializers.URLField()
    width = serializers.IntegerField()
    height = serializers.IntegerField()


class MessageSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    message = serializers.CharField()
    created_at = serializers.DateTimeField()
    attachment_images = AttachmentImageSerializer(many=True)
    user_id = serializers.IntegerField()


class UserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    first_name = serializers.CharField()
    preferred_locale = serializers.CharField()
    location = serializers.CharField()


class ThreadSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    business_purpose = serializers.CharField(default="booking_direct_thread", required=False)
    updated_at = serializers.DateTimeField()
    last_message_sent_at = serializers.DateTimeField()
    users = UserSerializer(many=True)
    attachment = AttachmentSerializer()
    messages = MessageSerializer(many=True)


class MessageApiSerializer(serializers.Serializer):
    message = MessageSerializer()


class ThreadApiSerializer(serializers.Serializer):
    thread = ThreadSerializer()


class ThreadsApiSerializer(serializers.Serializer):
    threads = ThreadSerializer(many=True)


class DetailedDescriptionSerializer(serializers.Serializer):
    name = serializers.CharField(required=False)
    summary = serializers.CharField(max_length=250, required=False)
    space = serializers.CharField(required=False)
    access = serializers.CharField(required=False)
    interaction = serializers.CharField(required=False)
    neighborhood_overview = serializers.CharField(required=False)
    transit = serializers.CharField(required=False)
    notes = serializers.CharField(required=False)
    house_rules = serializers.CharField(required=False)


class ReservationSerializer(serializers.ModelSerializer):
    def to_internal_value(self, data):
        data["standard_fees_details"] = json.dumps(data["standard_fees_details"])
        data["transient_occupancy_tax_details"] = json.dumps(
            data["transient_occupancy_tax_details"]
        )
        data["guest_phone_numbers"] = json.dumps(data["guest_phone_numbers"])
        return super().to_internal_value(data)

    class Meta:
        model = Reservation
        exclude = ("id", "date_created", "date_updated")


class MeUserSerializer(serializers.Serializer):

    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField()
    managed_business_entity_id = serializers.CharField(allow_null=True)
    phone = serializers.CharField(allow_null=True, allow_blank=True)
    picture_url = serializers.URLField()
    picture_url_large = serializers.URLField()

    def create(self, validated_data):
        account = self.context
        account.first_name = validated_data["first_name"]
        account.last_name = validated_data["last_name"]
        account.email = validated_data["email"]
        account.phone = validated_data["phone"]
        account.image_url = validated_data["picture_url"]
        account.image_url_large = validated_data["picture_url_large"]
        account.save()
        return validated_data


class WebhookHandler:
    def __init__(self, action, validated_data):
        self._action = {
            "import": self._fetch,
            "export": self._export,
            "link": self._link,
            "unlink": self._unlink,
        }.get(action, self._unlink)

        self.validated_data = validated_data
        self.external_id = validated_data["channel_id"]
        self.channel_app = validated_data["channel_app"]

    def __call__(self):
        self._action()

    def _get_airbnb_service(self):
        return self.channel_app.service

    def _create_sync(self):
        data = dict(
            prop=self.validated_data["id"],
            organization=self.channel_app.organization,
            sync_enabled=True,
            account=self.channel_app,
        )
        self.airbnb_sync = models.AirbnbSync.objects.create(**data)

    def _link_setup(self):
        service = self._get_airbnb_service()
        service.push_link(self.external_id)
        self.airbnb_sync.external_id = self.external_id
        self.airbnb_sync.save()

    def _link(self):
        self._create_sync()
        self._link_setup()
        self._publish()
        self._update()

    def _update(self):
        sync_id = self.airbnb_sync.id
        from .tasks import sync_pricing, sync_calendar, sync_availability

        sync_calendar.delay(sync_id)
        sync_pricing.delay(sync_id)
        sync_availability.delay(sync_id)
        # service = self._get_airbnb_service()
        # # TODO might not be a good enough check
        # service.update_listing(service.to_airbnb(self.validated_data["id"]))

    def _publish(self):
        service = self._get_airbnb_service()
        service.push_review_status(self.external_id)

    def _export(self,):
        prop = self.validated_data["id"]
        airbnb = self._get_airbnb_service()

        # with suppress(Listing.DoesNotExist):
        #     airbnb.push_listing_status(prop.airbnb_listing.external_id, False)
        #     airbnb.push_unlink(prop.airbnb_listing.external_id)
        #     prop.airbnb_listing.delete()

        airbnb_listing = AirbnbListingSerializer(prop).data
        serializer = ListingSerializer(data=airbnb_listing)
        self._create_sync()
        if serializer.is_valid():
            extras = airbnb_listing.pop("extras")
            listing = airbnb.push_listing(airbnb_listing)
            self.external_id = listing.get("id")
            # prop = self._create_models(airbnb_id)
            # if self.external_id:
            #     self._listing_setup(prop)
            self._link_setup()
            airbnb.push_listing_extras(extras, self.external_id)
            self._publish()
        else:
            self.airbnb_sync.approval_status = ListingApprovalStatus.not_ready.value
            self.airbnb_sync.save()
            logger.warn(
                f"Can't export listing {self.external_id} due to unmet reqs: {serializer.errors}"
            )

    def _unlink(self,):
        prop = self.validated_data["id"]
        airbnb_sync = models.AirbnbSync.objects.get(
            prop=prop, organization=self.channel_app.organization
        )
        service = self._get_airbnb_service()
        service.push_unlink(airbnb_sync.external_id)
        airbnb_sync.delete()

    def _fetch(self):
        service = self._get_airbnb_service()
        listing = service.get_detailed_listing(self.external_id)
        listing.update(listing.pop("extras", {}))

        airbnb_listing = Listing(owner=self.channel_app, data=listing)

        if "id" not in listing:
            logger.warn("Could not fetch from Airbnb: %s", self.external_id)

        serializer = PropertyCreateSerializer(
            data=service.to_cozmo(listing), context=self.validated_data
        )
        if serializer.is_valid():
            self.validated_data["id"] = serializer.save()
            airbnb_listing.save()
            self._create_sync()
            self._link_setup()
            self._publish()
        else:
            logger.warning(
                "Could not fetch from Airbnb %s: %s", self.external_id, serializer.errors
            )


class AirbnbAppDetailedSerializer(serializers.ModelSerializer):
    class Meta:
        model = AirbnbAccount
        exclude = ("access_token", "refresh_token", "user_id", "session", "organization")


class LinkSerializer(serializers.Serializer):

    does_not_exist_error = "Does not exist"

    id = serializers.PrimaryKeyRelatedField(queryset=Property.objects.active(), allow_null=True)
    channel_id = serializers.CharField(allow_null=True)
    channel_app = serializers.PrimaryKeyRelatedField(queryset=AirbnbAccount.objects.all())
    organization = serializers.HiddenField(default=DefaultOrganization())
    action = ChoicesField(
        choices=(
            ("import", "import"),
            ("export", "export"),
            ("link", "link"),
            ("unlink", "unlink"),
        ),
        required=False,
        allow_null=True,
        default=None,
    )

    def validate(self, data):
        prop = data["id"]
        organization = data["organization"]
        channel_app = data["channel_app"]
        if prop is None:
            if data["channel_id"] is None:
                raise serializers.ValidationError("Set at least one of: 'id', 'channel_id'")
        elif prop.organization != organization:
            raise serializers.ValidationError({"id": self.does_not_exist_error})

        if channel_app is None or channel_app.organization != organization:
            raise serializers.ValidationError({"channel_app": self.does_not_exist_error})

        if data["action"] is None:
            if data["id"] and data["channel_id"]:
                data["action"] = "link"
            elif data["id"] and not data["channel_id"]:
                data["action"] = "export"
            elif not data["id"] and data["channel_id"]:
                data["action"] = "import"
        return data

    def create(self, validated_data):
        # channel_id = validated_data["channel_id"]
        # channel_app = validated_data["channel_app"]

        handler = WebhookHandler(validated_data["action"], validated_data)
        handler()

        # if channel_id:
        #     airbnb = AirbnbService(channel_app.user_id, channel_app.access_token)
        #     sync_reservations(airbnb, validated_data["id"], validated_data)
        validated_data["id"].save()

        return {
            name: self.fields[name].to_representation(value)
            for name, value in validated_data.items()
            if not self.fields[name].write_only
        }


class FetchSerializer(serializers.Serializer):
    def _get_full_address(self, listing):
        street = listing["street"]
        apartment = listing["apt"]
        city = listing["city"]
        state = listing["state"]
        zipcode = listing["zipcode"]
        country = listing["country_code"]

        full_street = (street or "") + (f" {apartment}" if apartment else "")
        address_components = [city, state, zipcode, country]
        if len(full_street) > 0:
            address_components.insert(0, full_street)
        return ", ".join(filter(None.__ne__, address_components))

    @property
    def data(self):
        mapped_ids = (
            self.instance.organization.property_set.annotate(
                air_id=ExpressionWrapper(F("airbnb_sync__external_id"), output_field=CharField())
            )
            .filter(air_id__isnull=False)
            .values_list("air_id", flat=True)
        )
        listings = self.instance.service.get_listings()
        return [
            {
                "id": listing["id"],
                "name": listing["name"],
                "bedrooms": listing["bedrooms"],
                "bathrooms": listing["bathrooms"],
                "street": listing["street"],
                "apartment": listing["apt"],
                "city": listing["city"],
                "state": listing["state"],
                "zipcode": listing["zipcode"],
                "latitude": listing["lat"],
                "longitude": listing["lng"],
                "country_code": listing["country_code"],
                "full_address": self._get_full_address(listing),
                "listed": listing["has_availability"],
                # "cover_image": listing["photos"][0]["small_url"] if listing["photos"] else None,
                "sync_category": listing["synchronization_category"],
            }
            for listing in listings
            if str(listing["id"]) not in mapped_ids
        ]


class ContentSyncSerializer(serializers.Serializer):
    def create(self, validated_data):
        return dict()


class AvailabilitySyncSerializer(serializers.Serializer):
    def create(self, validated_data):
        return dict()


class PricingSyncSerializer(serializers.Serializer):
    def create(self, validated_data):
        return dict()


class SyncSerializer(serializers.Serializer):
    prop_id = serializers.PrimaryKeyRelatedField(
        queryset=Property.objects.active(), allow_null=True
    )
    sync_items = serializers.ListField(
        child=ChoicesField(choices=choices.SyncItem.choices()), allow_empty=True
    )
    organization = serializers.HiddenField(default=DefaultOrganization())

    def __init__(self, *args, **kwargs):
        self.user_id = kwargs.pop("user_id", None)
        self.access_token = kwargs.pop("access_token", None)
        super(serializers.Serializer, self).__init__(*args, **kwargs)

    def _sync_reservations(self, validated_data):
        prop = validated_data["prop_id"]
        service = AirbnbService(self.user_id, self.access_token)
        return sync_reservations(service, prop, validated_data)

    def _get_sync_handlers(self, sync_items):
        mapping = {
            SyncItem.reservations: self._sync_reservations,
            SyncItem.pricing: PricingSyncSerializer,
            SyncItem.content: ContentSyncSerializer,
            SyncItem.availability: AvailabilitySyncSerializer,
        }
        if "all" in sync_items:
            handlers = mapping.values()
        else:
            handlers = [mapping.get(item) for item in sync_items]
        return handlers

    def validate(self, data):
        prop = data["prop_id"]
        organization = data["organization"]
        if prop is None:
            raise serializers.ValidationError("Set at least one of: 'prop_id'")
        elif prop.organization != organization:
            raise serializers.ValidationError({"id": self.does_not_exist_error})
        return data

    def create(self, validated_data):
        items = validated_data["sync_items"]

        data = list()
        handlers = self._get_sync_handlers(items)
        for each in handlers:
            each(validated_data)

        return data


class AuthRequestSerializer(serializers.Serializer):
    organization = serializers.HiddenField(default=DefaultOrganization())


class AirbnbActionSerializer(serializers.Serializer):
    prop_id = serializers.PrimaryKeyRelatedField(
        queryset=Property.objects.active(), allow_null=True
    )
    organization = serializers.HiddenField(default=DefaultOrganization())

    def validate(self, data):
        prop = data["prop_id"]
        organization = data["organization"]
        if prop is None:
            raise serializers.ValidationError("Set at least one of: 'prop_id'")
        elif prop.organization != organization:
            raise serializers.ValidationError({"id": self.does_not_exist_error})
        return data


class AirbnbSyncSerializer(serializers.Serializer):
    id = serializers.PrimaryKeyRelatedField(queryset=Property.objects.active(), allow_null=True)
    organization = serializers.HiddenField(default=DefaultOrganization())
    sync_items = serializers.ListField(
        allow_empty=True, child=ChoicesField(choices=choices.SyncItem), allow_null=False
    )

    def validate(self, data):
        prop = data["id"]
        organization = data["organization"]
        if prop is None:
            raise serializers.ValidationError("Set at least one of: 'id'")
        elif prop.organization != organization:
            raise serializers.ValidationError({"id": self.does_not_exist_error})
        return data


class AirbnbMessageSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    user_id = serializers.IntegerField()
    message = serializers.CharField()
    created_at = serializers.DateTimeField()
    attachment_images = serializers.ListField(allow_empty=True)


class AirbnbBookingDetailSerializer(serializers.Serializer):
    listing_id = serializers.IntegerField(allow_null=True)
    listing_name = serializers.CharField(allow_null=True)
    checkin_date = serializers.DateField(allow_null=True)
    checkout_date = serializers.DateField(allow_null=True)
    expected_payout_amount_accurate = serializers.CharField(allow_null=True)
    non_response_at = serializers.DateTimeField(allow_null=True)
    nights = serializers.IntegerField(allow_null=True)
    number_of_guests = serializers.IntegerField(allow_null=True)
    number_of_adults = serializers.IntegerField(allow_null=True)
    number_of_children = serializers.IntegerField(allow_null=True)
    number_of_infants = serializers.IntegerField(allow_null=True)
    reservation_confirmation_code = serializers.CharField(allow_null=True)


class AirbnbRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=MessageRole.choices())
    user_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=True)


class AirbnbAttachmentSerializer(serializers.Serializer):
    booking_details = AirbnbBookingDetailSerializer()
    type = serializers.ChoiceField(choices=MessageAttachmentType.choices())
    status = serializers.ChoiceField(
        choices=MessageReservationStatus.choices() + MessageInquiryStatus.choices()
    )
    roles = serializers.ListField(child=AirbnbRoleSerializer())


class AirbnbUserSerializer(serializers.Serializer):
    first_name = serializers.CharField()
    id = serializers.IntegerField()
    location = serializers.CharField(allow_null=True)
    preferred_locale = serializers.CharField()  # TODO add locale enums


class AirbnbThreadSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    business_purpose = serializers.ChoiceField(choices=MessageBusinessPurpose.choices())
    updated_at = serializers.DateTimeField()
    last_message_sent_at = serializers.DateTimeField()
    users = serializers.ListField(child=AirbnbUserSerializer())
    attachment = AirbnbAttachmentSerializer()


class AirbnbListingSerializer(serializers.ModelSerializer):
    def airbnb_listing_attr(self, name):
        instance = self.instance
        with suppress(AirbnbSync.DoesNotExist):
            airbnb_listing = instance.airbnb_sync.get()
            return getattr(airbnb_listing, name)
        return None

    def _basic_listing_info(self):
        instance = self.instance
        prop_type = mappings.cozmo_airbnb_property_type[instance.property_type]
        location = instance.location
        pricing_settings = instance.pricing_settings
        basic_amenities = instance.basic_amenities
        external_id = self.airbnb_listing_attr("external_id")
        airbnb_data = {
            "synchronization_category": AirbnbSyncCategory(
                self.airbnb_listing_attr("scope") or 1
            ).pretty_name,
            "name": instance.name,
            "property_type_group": mappings.type_to_group[prop_type],
            "property_type_category": prop_type,
            "room_type_category": mappings.cozmo_rental_type.get(instance.rental_type),
            "bedrooms": int(instance.bedrooms),
            "bathrooms": float(instance.bathrooms),
            "beds": instance.room_set.count(),
            "amenity_categories": [
                airbnb_amenity.value
                for airbnb_amenity in Amenity
                if getattr(basic_amenities, airbnb_amenity.name, False)
            ],
            # "check_in_option": None,
            "requested_approval_status_category": StatusCategory.new.pretty_name,
            # "has_availability": False,  # TODO
            "permit_or_tax_id": instance.license_number,
            # Location
            "apt": getattr(location, "apartment", ""),
            "street": getattr(location, "address", ""),
            "city": getattr(location, "city", ""),
            "state": getattr(location, "state", ""),
            "zipcode": getattr(location, "postal_code", ""),
            "country_code": getattr(location, "country_code", ""),
            "lat": (
                str(location.latitude.quantize(Decimal("1.000000")))
                if getattr(location, "latitude", None)
                else ""
            ),
            "lng": (
                str(location.longitude.quantize(Decimal("1.000000")))
                if getattr(location, "longitude", None)
                else ""
            ),
            "user_defined_location": bool(location and location.latitude and location.longitude),
            "directions": str(instance.arrival_instruction or ""),
            "person_capacity": instance.max_guests or 1,
            "listing_currency": pricing_settings.currency or "USD",
            "listing_price": int(pricing_settings.nightly or 0),
            # "bathroom_shared": None,  # TODO special circumstances
            # "bathroom_shared_with_category": None,  # TODO special circumstances
            # "common_spaces_shared": None,  # TODO special circumstances
            # "common_spaces_shared_with_category": None,  # TODO special circumstances
            # "total_inventory_count": None,  # TODO special circumstances
            "property_external_id": str(instance.id),  # TODO correct mapping
        }
        if external_id:
            airbnb_data["id"] = external_id
        return airbnb_data

    def _listing_descriptions(self):
        instance = self.instance
        descriptions = instance.descriptions
        data = {
            "name": descriptions.name or instance.name,
            "summary": descriptions.summary or descriptions.headline,
            "space": descriptions.space,
            "access": descriptions.access,
            "interaction": descriptions.interaction,
            "neighborhood_overview": descriptions.neighborhood,
            "transit": descriptions.transit,
            "notes": descriptions.notes,
            "house_rules": descriptions.house_manual,
        }
        if descriptions.description:
            data["description"] = descriptions.description
        return data

    def _listing_photos(self):
        instance = self.instance
        images = instance.image_set
        data = [
            {
                "content_type": mimetypes.guess_type(img.url.name)[0],
                "filename": img.url.name,
                "image": b64encode(img.url.file.read()).decode(),
                "caption": img.caption,
                "sort_order": img.order,
            }
            for img in images.self_hosted().all()
            # for img in images.self_hosted().all() if img.url.file.size > 0
            # for img in images.self_hosted().filter(date_updated__gt=to_update)
        ]
        external_id = self.airbnb_listing_attr("external_id")
        if external_id:
            for each in data:
                each["listing_id"] = external_id
        return data

    def _listing_rooms(self):
        instance = self.instance
        rooms = instance.room_set
        external_id = self.airbnb_listing_attr("external_id")

        def get_beds(beds):
            beds_ret = dict()
            for bed in beds:
                bed_name = mappings.cozmo_to_airbnb_bed_names[bed]
                if bed_name not in beds_ret:
                    beds_ret[bed_name] = 0
                beds_ret[bed_name] += 1
            return [{"type": k, "quantity": v} for k, v in beds_ret.items()]

        # Each non-common room should have a unique index starting at 1
        def get_room_index_generator():
            max_rooms = 20
            for i in range(1, max_rooms + 1):
                yield i

        room_index = get_room_index_generator()

        data = [
            {
                "room_number": 0 if r.room_type == Room.Types.Common else next(room_index),
                "beds": get_beds(r.beds),
                "room_amenities": [{"quantity": 1, "type": "en_suite_bathroom"}]
                if r.bathrooms >= 1
                else list(),
            }
            for r in rooms.all()
        ]

        if external_id:
            for each in data:
                each["listing_id"] = external_id

        return data

    def _booking_settings(self):
        instance = self.instance
        booking_settings = instance.booking_settings
        check_out_until = booking_settings.check_in_out.check_out_until
        check_in_from = booking_settings.check_in_out.check_in_from
        check_in_to = booking_settings.check_in_out.check_in_to
        suitability = instance.suitability
        suitability_yes = Suitability.SuitabilityProvided.Yes.value
        data = {
            "cancellation_policy_category": mappings.cozmo_cancellation_policy[
                booking_settings.cancellation_policy
            ]
            or CancellationPolicy.flexible.value,
            "check_in_time_start": str(int(check_in_from[:2])) if check_in_from else "FLEXIBLE",
            "check_in_time_end": str(int(check_in_to[:2])) if check_in_to else "FLEXIBLE",
            "check_out_time": int(check_out_until[:2]) if check_out_until else None,
            "instant_book_welcome_message": booking_settings.instant_booking_welcome,
            "listing_expectations_for_guests": [],
            "guest_controls": {
                "allows_children_as_host": suitability.kids == suitability_yes,
                "allows_infants_as_host": suitability.infants == suitability_yes,
                "allows_smoking_as_host": suitability.smoking == suitability_yes,
                "allows_pets_as_host": suitability.pets == suitability_yes,
                "allows_events_as_host": suitability.events == suitability_yes,
            },
        }

        if booking_settings.instant_booking_allowed:
            data["instant_booking_allowed_category"] = "everyone"
        # If home is not suitable for kids or infants, add children_not_allowed_details field.
        if suitability.kids != suitability_yes or suitability.infants != suitability_yes:
            data["guest_controls"][
                "children_not_allowed_details"
            ] = suitability.children_not_allowed_details
        return data

    def _availability_rules(self):
        instance = self.instance
        availability_settings = instance.availability_settings
        advance_notice = availability_settings.advance_notice

        def get_distant_requests(value):
            values = {"1000": -1, "0": 0, "3": 90, "6": 180, "12": 365}
            return values.get(str(value), -1)

        data = {
            "default_min_nights": availability_settings.min_stay,
            "default_max_nights": availability_settings.max_stay,
            "booking_lead_time": {
                "hours": advance_notice * 24 if advance_notice else 0,
                "allow_request_to_book": 0,  # TODO
            },
            "max_days_notice": {
                # -1 anytime in future, 0 no future, 90/180/365 3mo, 6mo, 12mo
                "days": get_distant_requests(availability_settings.booking_window_months)
            },
            "seasonal_min_nights": list(),  # TODO
            "turnover_days": {"days": availability_settings.preparation},
            "day_of_week_check_in": [
                {"day_of_week": x} for x in availability_settings.check_in_days
            ],
            "day_of_week_check_out": [
                {"day_of_week": x} for x in availability_settings.check_out_days
            ],
            # "day_of_week_min_nights": [  # TODO
            #     {
            #         "day_of_week": 0,
            #         "min_nights": 0
            #     }
            # ]
        }
        return data

    def _standard_fees(self):
        """
        Partners can provide Standard fees that will apply to reservations on
        top of the stay price. Fees can be specified as either percentage of the
        nightly price (after all adjustments) or a flat amount per reservation.
        """
        instance = self.instance
        standard_fees = list()
        fees = Fee.objects.filter(prop=instance)
        for fee in fees:
            is_percentage = fee.is_percentage
            fee_type = mappings.cozmo_to_airbnb_fee_types[fee.fee_tax_type]
            is_linen_fee = fee_type == FeeType.linen_fee.value
            is_not_valid_linen_fee = is_linen_fee and is_percentage
            # TODO should add this to serializer check and can only have one of each category
            if is_not_valid_linen_fee:
                continue
            data = {
                "fee_type": mappings.cozmo_to_airbnb_fee_types[fee.fee_tax_type],
                "amount": int(fee.value) if is_percentage else int(fee.value) * int(1e6),
                "amount_type": AmountType.percent.value
                if is_percentage
                else AmountType.flat.value,
            }
            standard_fees.append(data)
        return standard_fees

    def _pricing_settings(self):
        instance = self.instance
        pricing_settings = instance.pricing_settings
        data = {
            "default_daily_price": pricing_settings.nightly,
            "cleaning_fee": pricing_settings.cleaning_fee,
            "guests_included": pricing_settings.included_guests,
            "security_deposit": pricing_settings.security_deposit,
            "price_per_extra_person": pricing_settings.extra_person_fee,
            "weekend_price": pricing_settings.weekend,
            "monthly_price_factor": None,
            "weekly_price_factor": None,
        }
        ret = {k: int(v) for k, v in data.items() if v is not None}
        ret["listing_currency"] = pricing_settings.currency
        ret["standard_fees"] = self._standard_fees()

        return ret

    def _calendar_operations(self):
        instance = self.instance
        # to_update = timezone.now() - timedelta(hours=2)

        today = timezone.now().today()
        max_date = today + timedelta(days=365 * 2)
        # if (

        #         not instance.reservation_set.all().exists()
        #         and not instance.blocking_set.all().exists()
        # ):
        #     return data

        def prepare_qs(qs):
            today = timezone.now().today()
            max_date = today + timedelta(days=365 * 2)

            return (
                qs.filter(end_date__gte=today, end_date__lte=max_date)
                .annotate(start=Greatest("start_date", today), end=Least("end_date", max_date))
                .values("start", "end")
            )

        def parse_dates(ev) -> str:
            if (ev["end"] - ev["start"]).days > 1:
                dates = "{}:{}".format(
                    ev["start"].date().isoformat(),
                    (ev["end"] - timedelta(days=1)).date().isoformat(),
                )
            else:
                dates = ev["start"].date().isoformat()
            return dates

        data = list()
        data.append(
            {
                "dates": [f"{today.date().isoformat()}:{max_date.date().isoformat()}"],
                "availability": "available",
                "notes": "",
            }
        )

        reservations_dates = [parse_dates(ev) for ev in prepare_qs(instance.reservation_set)]
        if reservations_dates:
            data.append(
                {
                    "dates": reservations_dates,
                    "availability": "unavailable",
                    "notes": "Cozmo reservations",
                }
            )
        blockings_dates = [
            parse_dates(ev)
            for ev in prepare_qs(
                instance.blocking_set.annotate(
                    start_date=Lower("time_frame"), end_date=Upper("time_frame")
                )
            )
        ]
        if blockings_dates:
            data.append(
                {
                    "dates": blockings_dates,
                    "availability": "unavailable",
                    "notes": "Cozmo blockings",
                }
            )

        external_calendar_set = instance.cozmo_calendar.externalcalendar_set.values_list("pk")
        external_blocking_dates = [
            parse_dates(ev)
            for ev in prepare_qs(
                ExternalCalendarEvent.objects.filter(external_cal__in=external_calendar_set)
            )
        ]
        if external_blocking_dates:
            data.append(
                {
                    "dates": external_blocking_dates,
                    "availability": "unavailable",
                    "notes": "Cozmo iCal blockings",
                }
            )

        return data

    def to_representation(self, instance):
        data = {
            **self._basic_listing_info(),
            "extras": {
                "photos": self._listing_photos(),
                "listing_descriptions": self._listing_descriptions(),
                "pricing_settings": self._pricing_settings(),
                "booking_settings": self._booking_settings(),
                "listing_rooms": self._listing_rooms(),
                "availability_rules": self._availability_rules(),
                "calendar_operations": self._calendar_operations(),
            },
        }
        return data

    class Meta:
        model = models.Property
        fields = (
            "id",
            "name",
            "descriptions",
            "status",
            "cover_image",
            "thumbnail",
            "owner",
            "scheduling_assistant",
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
        )
        read_only_fields = ("organization", "external_id")
        extra_kwargs = {"rental_type": {"required": True}}


class AirbnbListingReviewSerializer(BaseListingReviewSerializer):
    def validate_photos(self, photos):
        errors = list()
        if len(photos) < MIN_PHOTOS:
            errors.append(MinPhotoValidationError())
        for each in photos:
            pass  # TODO

        if errors:
            raise serializers.ValidationError(errors)
        return photos

    def validate_permits(self, permit):
        return permit

    def validate_amenities(self, amenities):
        if len(amenities) < MIN_AMENITIES:
            raise MinAmenitiesValidationError()
        return amenities

    def validate_description(self, description):
        if len(description) < MIN_DESCRIPTION:
            raise MinDescriptionValidationError()
        return description

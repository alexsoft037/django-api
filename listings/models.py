import logging
import os.path
import uuid
from collections import Counter, OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import auto
from functools import reduce
from hashlib import md5
from io import BytesIO
from itertools import chain, zip_longest

import icalendar
from PIL import Image as PilImage
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.postgres.fields import ArrayField, DateRangeField
from django.contrib.postgres.indexes import BrinIndex
from django.core.exceptions import ValidationError
from django.core.files.storage import get_storage_class
from django.core.validators import FileExtensionValidator, MaxValueValidator
from django.db import models, transaction
from django.db.models.aggregates import Sum
from django.db.models.expressions import F, Value
from django.utils import timezone

from accounts.models import Organization
from accounts.profile.models_base import PaymentSetting
from cozmo.storages import UploadImageTo
from cozmo_common.db.fields import PhoneField
from cozmo_common.db.models import TimestampModel
from cozmo_common.functions import date_range
from cozmo_common.mixins import ChangedFieldMixin
from cozmo_common.utils import get_ical_friendly_date
from listings.choices import CancellationReasons, LaundryType, ParkingType
from rental_integrations.exceptions import ServiceException
from . import choices, querysets
from .fields import FalseBooleanField, HourField
from .managers import FeeManager, ProductionManager, TaxManager
from .models_base import BaseAvailability, BaseDiscount, BaseFee, BasePricingSettings

logger = logging.getLogger(__name__)
User = get_user_model()
StorageBackend = get_storage_class()


class Group(TimestampModel, PaymentSetting):
    """Property Group"""

    name = models.CharField(max_length=50)
    description = models.TextField(default="", blank=True)
    cancellation_policy = models.CharField(
        max_length=2,
        choices=choices.CancellationPolicy.choices(),
        default=choices.CancellationPolicy.Unknown.value,
        blank=True,
    )

    # external_id for syncing purposes
    external_id = models.CharField(default="", editable=False, max_length=100)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    class Meta:
        permissions = (("group_access", "Can access group"), ("view_group", "Can view groups"))


class ListingDescriptions(TimestampModel):
    name = models.CharField(max_length=100, default="", blank=True)
    headline = models.CharField(max_length=150, default="", blank=True)
    summary = models.TextField(default="", blank=True)
    space = models.TextField(default="", blank=True)
    access = models.TextField(default="", blank=True)
    interaction = models.TextField(default="", blank=True)
    neighborhood = models.TextField(default="", blank=True)
    transit = models.TextField(default="", blank=True)
    notes = models.TextField(default="", blank=True)
    house_rules = models.TextField(default="", blank=True)
    description = models.TextField(default="", blank=True)
    additional_amenities = models.TextField(default="", blank=True)
    things_to_do = models.TextField(default="", blank=True)
    house_manual = models.TextField(default="", blank=True)
    prop = models.OneToOneField(
        "Property", on_delete=models.CASCADE, null=True, related_name="descriptions"
    )

    @property
    def combined_descriptions(self):
        descriptions = [
            (self.summary, "Description Summary"),
            (self.space, "Space overview"),
            (self.neighborhood, "Neighborhood overview"),
            (self.transit, "Getting around"),
            (self.access, "Guest access"),
            (self.interaction, "Interaction with guests"),
            (self.additional_amenities, "Additional amenities"),
            (self.notes, "Things to note"),
            (self.house_rules, "House rules"),
        ]

        combined_desc = reduce(
            lambda x, y: x + y,
            [[title.upper(), field] for field, title in descriptions if field],
            list(),
        )
        return "{}\n".format("\n\n".join(combined_desc))


class BookingSettings(TimestampModel):
    months_advanced_bookable = models.IntegerField(null=True, blank=True, default=6)
    cancellation_policy = models.CharField(
        max_length=2,
        choices=choices.CancellationPolicy.choices(),
        default=choices.CancellationPolicy.Unknown.value,
        blank=True,
    )
    # if false, reservation approval process is required
    instant_booking_allowed = models.BooleanField(default=False)
    instant_booking_welcome = models.TextField(default="", blank=True)
    prop = models.OneToOneField(
        "Property", on_delete=models.CASCADE, null=True, related_name="booking_settings"
    )


class AvailabilitySettings(BaseAvailability):
    prop = models.OneToOneField(
        "Property", on_delete=models.CASCADE, null=True, related_name="availability_settings"
    )


class Property(ChangedFieldMixin, TimestampModel, PaymentSetting):
    """A place for rental."""

    Statuses = choices.PropertyStatuses
    Rentals = choices.Rentals
    Types = choices.PropertyTypes

    status = models.PositiveSmallIntegerField(
        choices=Statuses.choices(), default=Statuses.Active.value
    )
    floor = models.IntegerField(null=True, blank=True)
    name = models.CharField(max_length=150, blank=True, default="")
    location = models.ForeignKey("Location", null=True, blank=True, on_delete=models.SET_NULL)
    size = models.IntegerField(null=True, blank=True)

    locale = models.CharField(max_length=2, blank=True)
    # TODO support timezone choices
    time_zone = models.CharField(max_length=50, null=True, blank=True, default="")
    property_type = models.CharField(max_length=2, choices=Types.choices())
    rental_type = models.CharField(
        max_length=2, choices=Rentals.choices(), default=Rentals.Other.value
    )

    max_guests = models.IntegerField(null=True, blank=True)
    external_id = models.CharField(max_length=255, blank=True, default="")
    legacy_id = models.CharField(max_length=255, blank=True, default="", editable=False)
    license_number = models.CharField(max_length=50, blank=True)

    bedrooms = models.DecimalField(max_digits=6, decimal_places=1, blank=True, default=0.0)
    bathrooms = models.DecimalField(max_digits=6, decimal_places=1, blank=True, default=0.0)
    inventory_count = models.PositiveSmallIntegerField(default=1, blank=True)

    building = models.ForeignKey("Building", null=True, blank=True, on_delete=models.SET_NULL)

    payment_methods = models.ManyToManyField("PaymentMethod", blank=True)

    # Amenities
    features = models.ManyToManyField("Feature", blank=True)

    owner = models.ForeignKey(
        "owners.Owner", null=True, blank=True, on_delete=models.SET_NULL, related_name="properties"
    )
    organization = models.ForeignKey(Organization, null=True, on_delete=models.SET_NULL)
    group = models.ForeignKey(
        Group, default=None, blank=True, null=True, on_delete=models.SET_NULL
    )

    # directions
    arrival_instruction = models.ForeignKey(
        "ArrivalInstruction", null=True, blank=True, on_delete=models.SET_NULL
    )

    rental_connection = models.ForeignKey(
        "rental_connections.RentalConnection",
        default=None,
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    is_sandbox = FalseBooleanField()

    channel_network_enabled = models.BooleanField(default=False)

    default_manager = models.Manager()
    objects = ProductionManager.from_queryset(querysets.PropertyQuerySet)()

    class Meta:
        verbose_name_plural = "properties"
        permissions = (
            ("public_api_access", "Can access data in Public API"),
            ("view_property", "Can view property"),
        )

    @property
    def full_address(self):
        if not self.location:
            return ""
        address_fields = [
            self.location.address,
            self.location.apartment,
            self.location.city,
            f"{self.location.state} {self.location.postal_code}".strip(),
            self.location.country_code,
        ]
        return ", ".join([field for field in address_fields if field]).strip()

    @property
    def cover_image(self):
        try:
            image_url = StorageBackend().url(
                self.image_set.all().values_list("url", flat=True).first()
            )
        except TypeError:
            image_url = None
        return image_url

    @property
    def thumbnail(self):
        try:
            image_url = StorageBackend().url(
                self.image_set.all().values_list("thumbnail", flat=True).first()
            )
        except TypeError:
            image_url = None
        return image_url

    @property
    def is_trip_advisor_sync_enabled(self):
        org = self.organization
        if hasattr(org, "plansettings") and org.plansettings.trip_advisor_sync:
            has_tripadvisor = hasattr(self, "tripadvisor")
            if has_tripadvisor and self.tripadvisor.sync_enabled or not has_tripadvisor:
                return True
        return False

    def fees_with_taxes(self):
        return self.additionalfee_set.exclude(
            calculation_method__in=(
                choices.CalculationMethod.Per_Stay_Percent.value,
                choices.CalculationMethod.Per_Stay_Only_Rates_Percent.value,
                choices.CalculationMethod.Per_Stay_No_Taxes_Percent.value,
            )
        ).filter(optional=False)

    def fees_without_taxes(self):
        return self.additionalfee_set.exclude(
            calculation_method__in=(
                choices.CalculationMethod.Per_Stay_Percent.value,
                choices.CalculationMethod.Per_Stay_Only_Rates_Percent.value,
                choices.CalculationMethod.Per_Stay_No_Taxes_Percent.value,
            ),
            fee_tax_type__in=(
                AdditionalFee.TaxTypes.Local_Tax.value,
                AdditionalFee.TaxTypes.Tourist_Tax.value,
                AdditionalFee.TaxTypes.VAT.value,
            ),
        ).filter(optional=False)

    # Percent Fees
    def per_stay_percent_fee(self):
        return self.additionalfee_set.filter(
            optional=False, calculation_method=choices.CalculationMethod.Per_Stay_Percent.value
        )

    def per_stay_only_rates_percent_fee(self):
        return self.additionalfee_set.filter(
            optional=False,
            calculation_method=choices.CalculationMethod.Per_Stay_Only_Rates_Percent.value,
        )

    def per_stay_no_taxe_percent_fees(self):
        return self.additionalfee_set.filter(
            optional=False,
            calculation_method=choices.CalculationMethod.Per_Stay_No_Taxes_Percent.value,
        )

    def sync(self):
        try:
            SyncLog.objects.create(prop=self, status=choices.SyncStatus.Pending)
            self.rental_connection.sync(self.external_id)
        except ServiceException:
            self.status = self.Statuses.Disabled
            self.save()
            SyncLog.objects.create(prop=self, status=choices.SyncStatus.Error)
        except AttributeError:
            pass
        else:
            SyncLog.objects.create(prop=self, status=choices.SyncStatus.Succes)

    def _get_related_objects_for_change_fields(self):
        return [
            "descriptions",
            "location",
            "booking_settings",
            "pricing_settings",
            "basic_amenities",
            "suitability",
        ]


# Payment-related models


class PricingSettings(BasePricingSettings):
    included_guests = models.IntegerField(null=True, blank=True)
    min_price = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    max_price = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    smart_pricing_enabled = FalseBooleanField()

    prop = models.OneToOneField(
        "Property", on_delete=models.CASCADE, null=True, related_name="pricing_settings"
    )


class Rate(BasePricingSettings):
    """Detailed pricing information for a property for a given period of time."""

    errors = {"no_rate": "No rate for {}"}

    label = models.CharField(max_length=100, default="", blank=True)
    seasonal = FalseBooleanField()
    smart = FalseBooleanField()

    time_frame = DateRangeField()
    prop = models.ForeignKey("Property", on_delete=models.CASCADE)

    default_manager = querysets.RateQuerySet.as_manager()
    objects = ProductionManager(lookup_field="prop__is_sandbox")

    def __str__(self):
        return str(self.time_frame)

    @classmethod
    def visit_price(cls, start_date, end_date, prop_id, month_days):
        """
        Calculate base price for renting a property for a given period.

        `start_date` is inclusive, `end_date` is exclusive. Raises `ValueError`
        if missing data for any day in a period.
        """
        from .utils import prepare_prices, split_by_ranges

        total = (end_date - start_date).days
        by_months = split_by_ranges(
            start_date,
            total,
            OrderedDict([("monthly", month_days), ("weekly", 7), ("nightly", 1)]),
        )
        by_weeks = split_by_ranges(start_date, total, OrderedDict([("weekly", 7), ("nightly", 1)]))
        by_nights = split_by_ranges(start_date, total, OrderedDict([("nightly", 1)]))

        visit_rates = cls.default_manager.visit_rates((start_date, end_date), prop_id).values(
            "time_frame", "nightly", "weekly", "monthly", "weekend"
        )

        seasonal_rates = cls.default_manager.seasonal_rates(
            (start_date, end_date), prop_id
        ).values("time_frame", "nightly", "weekly", "monthly", "weekend")
        try:
            default_rate = PricingSettings.objects.only("nightly").get(prop=prop_id).nightly
        except PricingSettings.DoesNotExist:
            default_rate = None

        rates = dict.fromkeys(date_range(start_date, end_date), default_rate)
        zip_rates = tuple(zip_longest(seasonal_rates, visit_rates))
        prices_by_months = prepare_prices(zip_rates, by_months)
        prices_by_weeks = prepare_prices(zip_rates, by_weeks)
        prices_by_nights = prepare_prices(zip_rates, by_nights)

        try:
            for visit_date in rates.keys():
                rates[visit_date] = min(
                    prices_by_months.get(visit_date, rates[visit_date]),
                    prices_by_weeks.get(visit_date, rates[visit_date]),
                    prices_by_nights.get(visit_date, rates[visit_date]),
                )
            price = sum(rates.values())
        except TypeError:
            missed_days = ", ".join(k.isoformat() for k, v in rates.items() if v is None)
            logger.info("Missing rate for: %s", missed_days)
            raise ValueError(cls.errors["no_rate"].format(missed_days))

        return price

    @classmethod
    def rate_per_day(cls, start_date, end_date, prop_id):
        """
        Return days mapped on Rate

        `start_date` is inclusive, `end_date` is exclusive. Raises `ValueError`
        if missing data for any day in a period.
        """
        visit_rates = cls.default_manager.visit_rates((start_date, end_date), prop_id)
        seasonal_rates = cls.default_manager.seasonal_rates((start_date, end_date), prop_id)

        try:
            default_rate = PricingSettings.objects.get(prop=prop_id)
        except PricingSettings.DoesNotExist:
            default_rate = None

        rates = dict.fromkeys(date_range(start_date, end_date), default_rate)

        rates.update(
            {
                visit_day: rate
                for rate in chain(seasonal_rates, visit_rates)
                for visit_day in date_range(
                    max(start_date, rate.time_frame.lower or date.min),
                    min(end_date, rate.time_frame.upper or date.max),
                )
            }
        )
        return rates

    @classmethod
    def visit_rates(cls, start_date, end_date, prop_id):
        """
        Return Rates with duration how many days were affected

        `start_date` is inclusive, `end_date` is exclusive. Raises `ValueError`
        if missing data for any day in a period.
        """

        rates = cls.rate_per_day(start_date, end_date, prop_id)

        if None in rates.values():
            missed_days = ", ".join(k.isoformat() for k, v in rates.items() if v is None)
            logger.info("Missing rate for: %s", missed_days)
            raise ValueError(cls.errors["no_rate"].format(missed_days))

        return Counter(rates.values())


def generate_code():
    return uuid.uuid4().hex[:12].upper()


class Reservation(ChangedFieldMixin, TimestampModel, PaymentSetting):
    """Declaration of stay in a property for a given time."""

    Statuses = choices.ReservationStatuses

    class DynamicStatuses(choices.IntChoicesEnum):
        Inquiry = auto()
        Pending = auto()
        Request = auto()
        Expired = auto()
        Reserved = auto()
        Cancelled = auto()

    class Sources(choices.IntChoicesEnum):
        App = auto()
        Web = auto()
        Airbnb = auto()
        VRBO = auto()
        Booking = auto()
        Tripadvisor = auto()
        Recommended = auto()
        Homeaway = auto()

    # class ReservationType(choices.IntChoicesEnum):
    #     Inquiry = auto()
    #     Reservation = auto()

    start_date = models.DateField()
    end_date = models.DateField()
    status = models.PositiveSmallIntegerField(
        choices=Statuses.choices(), default=Statuses.Accepted.value
    )
    # type = models.PositiveSmallIntegerField(
    #     choices=ReservationType.choices(), default=ReservationType.Inquiry.value
    # )

    guests_adults = models.IntegerField(default=0, blank=True)
    guests_children = models.IntegerField(default=0, blank=True)
    guests_infants = models.IntegerField(default=0, blank=True)
    pets = models.IntegerField(default=0, blank=True)
    guest = models.ForeignKey("crm.Contact", on_delete=models.SET_NULL, null=True)
    prop = models.ForeignKey("Property", on_delete=models.CASCADE, null=True)
    rebook_allowed_if_cancelled = models.BooleanField(default=True)
    external_id = models.CharField(
        max_length=255, blank=True, default="", help_text="Reference ID to an external reservation"
    )
    connection_id = models.CharField(max_length=255, blank=True, default="")

    confirmation_code = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        default=None,
        help_text="Friendly reservation identifier",
    )

    payments = GenericRelation("payments.Charge", object_id_field="payment_for_id")
    bank_transaction = models.ForeignKey(
        "payments.PlaidTransaction",
        blank=True,
        default=None,
        null=True,
        on_delete=models.SET_DEFAULT,
    )
    expiration = models.DateTimeField(null=True, blank=True)
    refund_deposit_after = models.PositiveIntegerField(null=True, blank=True, default=None)
    cancellation_policy = models.CharField(
        max_length=2,
        choices=choices.CancellationPolicy.choices(),
        default=choices.CancellationPolicy.Unknown.value,
        blank=True,
    )
    source = models.PositiveSmallIntegerField(choices=Sources.choices(), default=Sources.App.value)
    # payout_released = models.BooleanField(default=False)
    date_booked = models.DateTimeField(null=True, blank=True)

    price = models.DecimalField(
        max_digits=12, decimal_places=2, help_text="Total Price", null=True
    )
    paid = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, default=0.0, help_text="Total Paid By Guest"
    )

    cancellation_reason = models.PositiveSmallIntegerField(
        choices=CancellationReasons.choices(), null=True, default=None
    )
    cancellation_notes = models.TextField(blank=True, default="")

    base_total = models.DecimalField(
        max_digits=12, decimal_places=2, help_text="Total base price", null=True
    )
    default_manager = models.Manager()
    objects = ProductionManager(lookup_field="prop__is_sandbox")

    class Meta:
        permissions = (("view_reservation", "Can view reservations"),)

    def __str__(self):
        pk = getattr(self, "pk", None)
        return "<Reservation pk={}>".format(pk)

    @property
    def dynamic_status(self):
        """Dynamic Statuses"""
        statuses = self.Statuses
        dynamic = self.DynamicStatuses
        if self.status == statuses.Accepted:
            ret = dynamic.Reserved
        elif self.status == statuses.Inquiry_Blocked and not self.is_inquiry_expired:
            ret = dynamic.Pending
        elif self.status == statuses.Inquiry and not self.is_inquiry_expired:
            ret = dynamic.Inquiry
        elif self.is_inquiry_expired:
            ret = dynamic.Expired
        elif self.status in (statuses.Cancelled, statuses.Declined):
            ret = dynamic.Cancelled
        elif self.status == statuses.Request:
            ret = dynamic.Request
        else:
            raise ValueError("Invalid Reservation Status")
        return ret.pretty_name

    @property
    def days_to_stay(self):
        def parse(date):
            if isinstance(date, str):
                parsed = datetime.strptime(date, "%Y-%m-%d").date()
            else:
                parsed = date
            return parsed

        start = parse(self.start_date)
        end = parse(self.end_date)
        try:
            return (end - start).days
        except TypeError:
            raise ValueError("Unset start or/and end date")

    @property
    def organization(self):
        return self.prop.organization

    @property
    def nights(self):
        return (self.end_date - self.start_date).days

    @property
    def is_inquiry(self):
        return self.status in (self.Statuses.Inquiry_Blocked.value, self.Statuses.Inquiry.value)

    @property
    def is_inquiry_expired(self):
        now = timezone.now()
        return self.is_inquiry and self.expiration and self.expiration < now

    @property
    def active_cancellation_policy(self):
        unkown_policy = choices.CancellationPolicy.Unknown
        if self.cancellation_policy != unkown_policy:
            policy = self.cancellation_policy
        elif (
            hasattr(self.prop, "booking_settings")
            and self.prop.booking_settings.cancellation_policy != unkown_policy
        ):
            policy = self.prop.cancellation_policy
        elif self.prop.group and self.prop.group.cancellation_policy != unkown_policy:
            policy = self.prop.group.cancellation_policy
        elif hasattr(self.prop.organization, "plansettings"):
            policy = self.prop.organization.plansettings.cancellation_policy
        else:
            policy = unkown_policy
        return choices.CancellationPolicy(policy).pretty_name

    @property
    def guests(self):
        return self.guests_adults + self.guests_children + self.guests_infants

    @property
    def nightly_price(self):
        return (self.base_total / self.nights) if self.base_total else None

    @property
    def price_formatted(self):
        try:
            currency = choices.Currencies[self.prop.pricing_settings.currency].symbol
        except PricingSettings.DoesNotExist:
            currency = ""
        return f"{currency}{self.price}"

    @property
    def currency(self):
        try:
            currency = choices.Currencies[self.prop.pricing_settings.currency].value
        except PricingSettings.DoesNotExist:
            currency = ""
        return currency

    @property
    def send_email(self):
        return self._send_email if hasattr(self, "_send_email") else False

    @send_email.setter
    def send_email(self, value):
        self._send_email = value if isinstance(value, bool) else False

    @property
    def payment_requested(self):
        return self._payment_requested if hasattr(self, "_payment_requested") else False

    @payment_requested.setter
    def payment_requested(self, value):
        self._payment_requested = value if isinstance(value, bool) else False

    def calculate_discounts(self, rates_price, days_to_stay):
        discounts = Discount.objects.filter(prop_id=self.prop_id, optional=False)
        disc_percent = (
            discounts.filter(is_percentage=True)
            .annotate(partial_value=F("value") / Decimal("100") * Value(rates_price))
            .aggregate(total=Sum("partial_value"))
        )

        disc_fixed = (
            discounts.filter(is_percentage=False)
            .fixed_case(days_to_stay)
            .aggregate(total=Sum("partial_value"))
        )
        return (disc_fixed["total"] or 0) + (disc_percent["total"] or 0)

    def calculate_fees_with_taxes(self):
        return (
            self.prop.fees_with_taxes()
            .fixed_case(self.days_to_stay, self.guests)
            .aggregate(total=Sum("partial_value"))["total"]
            or 0
        )

    def calculate_fees_without_taxes(self):
        return (
            self.prop.fees_without_taxes()
            .fixed_case(self.days_to_stay, self.guests)
            .aggregate(total=Sum("partial_value"))["total"]
            or 0
        )

    def calculate_per_stay_percent_fee(self, total_value):
        return (
            self.prop.per_stay_percent_fee()
            .annotate(partial_value=F("value") / Decimal("100") * Value(total_value))
            .aggregate(total=Sum("partial_value"))["total"]
            or 0
        )

    def calculate_per_stay_only_rates_percent_fee(self, rates_value):
        return (
            self.prop.per_stay_only_rates_percent_fee()
            .annotate(partial_value=F("value") / Decimal("100") * Value(rates_value))
            .aggregate(total=Sum("partial_value"))["total"]
            or 0
        )

    def calculate_per_stay_no_taxes_percent_fee(self, total_value_without_tax):
        return (
            self.prop.per_stay_no_taxe_percent_fees()
            .annotate(partial_value=F("value") / Decimal("100") * Value(total_value_without_tax))
            .aggregate(total=Sum("partial_value"))["total"]
            or 0
        )

    @transaction.atomic
    def calculate_price(self, commit=False):
        """Calculate total price, including rates, fees, taxes and discounts."""

        if self.days_to_stay < 1:
            msg = "Invalid reservation {}: days_to_stay < 1".format(str(self))
            logger.info(msg)
            raise ValueError(msg)

        month_days = 30
        if (
            self.prop
            and self.prop.organization
            and hasattr(self.prop.organization, "plansettings")
        ):
            month_days = self.prop.organization.plansettings.month_days

        if self.base_total:
            rates_price = self.base_total
        else:
            rates_price = Rate.visit_price(
                self.start_date, self.end_date, self.prop_id, month_days
            )

        discount_value = self.calculate_discounts(rates_price, self.days_to_stay)

        # No % Fees
        fees_with_taxes = self.calculate_fees_with_taxes()
        # Only Fees, thay are not included in final price, only for fees_stay_no_taxes_percent
        fees = self.calculate_fees_without_taxes()

        # % Fees / I assume that they are not affecting themselves
        fees_per_stay_only_rate_percent = self.calculate_per_stay_only_rates_percent_fee(
            rates_price
        )
        fees_stay_no_taxes_percent = self.calculate_per_stay_no_taxes_percent_fee(
            fees + rates_price
        )
        fees_per_stay_percent = self.calculate_per_stay_percent_fee(fees_with_taxes + rates_price)

        reservation_fees = self.reservationfee_set.all()
        total_reservation_fees = sum(f.value for f in reservation_fees)
        total_refunds = sum(r.value for r in self.refunds.all())

        all_fees = (
            fees_with_taxes
            + fees_per_stay_percent
            + fees_per_stay_only_rate_percent
            + fees_stay_no_taxes_percent
            + total_reservation_fees
        )

        self.price = max(
            Decimal("0"), rates_price - discount_value + all_fees - total_refunds
        ).quantize(Decimal("0.01"))

        if commit:
            self.save()

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        """In case of confirmation_code duplication"""

        if self.days_to_stay < 1:
            msg = "Invalid reservation {}: days_to_stay < 1".format(str(self))
            logger.info(msg)
            raise ValueError(msg)

        try:
            self.validate_unique()
        except ValidationError as e:
            if e.error_dict["confirmation_code"]:
                self.confirmation_code = generate_code()
                self.save(force_insert, force_update, using, update_fields)
                return
        super().save(force_insert, force_update, using, update_fields)

    def to_ical(self):
        return icalendar.Event(
            {
                "SUMMARY": "Event - Voyajoy Reservation",
                "DTSTART;VALUE=DATE": get_ical_friendly_date(self.start_date),
                "DTEND;VALUE=DATE": get_ical_friendly_date(self.end_date),
                "DTSTAMP;VALUE=DATE-TIME": self.date_updated.isoformat(),
                "UID": "{}@voyajoy.com".format(
                    md5(
                        ":".join(
                            [
                                self.start_date.isoformat(),
                                self.end_date.isoformat(),
                                str(self.prop_id),
                            ]
                        ).encode()
                    ).hexdigest()  # nosec
                ),
            }
        )

    def _create_refunds(self, refund_data=None):
        self.refunds.bulk_create(
            ReservationRefund(reservation=self, **data) for data in refund_data
        )

    def _create_fees(self, fees_data=None):
        self.reservationfee_set.all().delete()
        if fees_data is not None:
            self.reservationfee_set.bulk_create(
                ReservationFee(reservation=self, **data) for data in fees_data
            )
            return

        total_rate = Decimal(self.base_total)

        fees_with_taxes = self.prop.fees_with_taxes().fixed_case(self.days_to_stay, self.guests)

        sum_fees = fees_with_taxes.aggregate(total=Sum("partial_value"))["total"] or 0

        # Per_Stay_Only_Rates_Percent amount / 100 * total_rate
        rate_percent_fees = self.prop.per_stay_only_rates_percent_fee().annotate(
            partial_value=F("value") / Decimal("100") * Value(total_rate)
        )

        # Per_Stay_Percent amount / 100 * (total_rate + sum_fees)
        stay_percent = self.prop.per_stay_percent_fee().annotate(
            partial_value=F("value") / Decimal("100") * Value(total_rate + sum_fees)
        )

        # Per_Stay_No_Taxes_Percent
        sum_no_tax_fees = (
            self.prop.fees_without_taxes()
            .fixed_case(self.days_to_stay, self.guests)
            .aggregate(total=Sum("partial_value"))["total"]
            or 0
        )

        no_tax_percent_fees = self.prop.per_stay_no_taxe_percent_fees().annotate(
            partial_value=F("value") / Decimal("100") * Value(total_rate + sum_no_tax_fees)
        )

        fees = (
            ReservationFee(
                name=fee.name,
                value=fee.partial_value,
                fee_tax_type=fee.fee_tax_type,
                refundable=fee.refundable,
                optional=fee.optional,
                taxable=fee.taxable,
                reservation=self,
            )
            for fee in chain(no_tax_percent_fees, stay_percent, rate_percent_fees, fees_with_taxes)
        )

        self.reservationfee_set.bulk_create(fees)

    def _create_discounts(self, discounts_data=None):
        self.reservationdiscount_set.all().delete()
        if discounts_data is not None:
            self.reservationdiscount_set.bulk_create(
                ReservationDiscount(reservation=self, **data) for data in discounts_data
            )
            return

        discounts = Discount.objects.filter(prop_id=self.prop_id)

        disc_percent = discounts.filter(is_percentage=True).annotate(
            partial_value=F("value") / Decimal("100") * Value(self.base_total)
        )
        disc_fixed = discounts.filter(is_percentage=False).fixed_case(self.days_to_stay)

        self.reservationdiscount_set.bulk_create(
            ReservationDiscount(
                value=discount.partial_value,
                discount_type=discount.discount_type,
                optional=discount.optional,
                reservation=self,
            )
            for discount in disc_percent
        )

        self.reservationdiscount_set.bulk_create(
            ReservationDiscount(
                value=discount.partial_value,
                discount_type=discount.discount_type,
                optional=discount.optional,
                reservation=self,
            )
            for discount in disc_fixed
        )

    def _calculate_base_total(self):
        visit_rates = Rate.visit_rates(self.start_date, self.end_date, self.prop_id)
        self.base_total = sum(duration * rate.nightly for rate, duration in visit_rates.items())

    def _get_price_total(self):
        """
        Get and set prices
        :return:
        """
        discount_data = self.reservationdiscount_set.all()
        fee_data = self.reservationfee_set.all()
        total_discounts = sum(d.value for d in discount_data) * -1
        total_fees = sum(f.value for f in fee_data)
        total_refunds = sum(r.value for r in self.refunds.all())
        total = sum([self.base_total, total_discounts, total_fees, (-1 * total_refunds)])
        return total

    def recalculate_price(self, commit=True):
        self.price = self._get_price_total()
        if commit:
            self.save()
        return self.price

    def create_charge_objects(self, rate_data=None):
        # self._create_rate(rate_data=rate_data)
        self._create_fees()
        self._create_discounts()


class PaymentMethod(models.Model):
    """A mean of a payment for renting a property."""

    name = models.CharField(max_length=100)


class Discount(TimestampModel, BaseDiscount):
    """A factor that can lower a base price (`Rate`) of a property."""

    days_before = models.SmallIntegerField()
    is_percentage = models.BooleanField(default=False)
    calculation_method = models.CharField(
        max_length=2,
        default=choices.CalculationMethod.Per_Stay.value,
        choices=choices.CalculationMethod.choices(),
        blank=True,
    )
    prop = models.ForeignKey("Property", on_delete=models.CASCADE)

    objects = querysets.FixedCaseQuerySet.as_manager()


class AdditionalFee(TimestampModel, BaseFee):
    """Any additional fees not included in a base price."""

    order = models.IntegerField(null=True, blank=True)
    calculation_method = models.CharField(
        max_length=2,
        default=choices.CalculationMethod.Per_Stay.value,
        choices=choices.CalculationMethod.choices(),
        blank=True,
    )
    prop = models.ForeignKey("Property", on_delete=models.CASCADE)

    default_manager = querysets.FeeTypeQuerySet.as_manager()
    objects = ProductionManager.from_queryset(querysets.FeeTypeQuerySet)(
        lookup_field="prop__is_sandbox"
    )

    @classmethod
    def create_default_fees(cls, prop) -> list:
        return cls.objects.bulk_create(
            (
                cls(
                    prop=prop,
                    value=15,
                    name="Hotel Tax",
                    calculation_method=choices.CalculationMethod.Per_Stay_Percent.value,
                    fee_tax_type=choices.TaxTypes.Hotel_Tax.value,
                ),
                cls(
                    prop=prop,
                    value=20,
                    name="Booking fee",
                    calculation_method=choices.CalculationMethod.Per_Stay.value,
                    fee_tax_type=choices.FeeTypes.Booking_Fee.value,
                ),
                cls(
                    prop=prop,
                    value=80,
                    name="Service fee",
                    calculation_method=choices.CalculationMethod.Per_Stay.value,
                    fee_tax_type=choices.FeeTypes.Service_Fee.value,
                ),
                cls(
                    prop=prop,
                    value=100,
                    name="Damage Protection Insurance Fee",
                    calculation_method=choices.CalculationMethod.Per_Stay.value,
                    fee_tax_type=choices.FeeTypes.Damage_Protection_Insurance_Fee.value,
                ),
            )
        )


class Fee(AdditionalFee):
    objects = FeeManager()

    class Meta:
        proxy = True


class Tax(AdditionalFee):
    objects = TaxManager()

    class Meta:
        proxy = True


class ReservationFee(BaseFee):
    """Fee related to Reservation"""

    fee_tax_type = models.CharField(
        max_length=3,
        choices=AdditionalFee.FEE_TAX_TYPES + choices.SecurityDepositTypes.choices(),
        default=choices.FeeTypes.Other_Fee.value,
    )
    custom = models.BooleanField(default=False)
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)


class ReservationRate(models.Model):
    """Rate related to Reservation"""

    duration = models.IntegerField(default=0)
    value = models.DecimalField(max_digits=9, decimal_places=2)

    reservation = models.OneToOneField(Reservation, on_delete=models.CASCADE)

    @property
    def nightly(self):
        if self.duration <= 1:
            nightly = self.value
        else:
            nightly = (self.value / self.duration).quantize(Decimal("0.00"))
        return nightly


class ReservationDiscount(models.Model):
    """Discount related to Reservation"""

    value = models.DecimalField(max_digits=8, decimal_places=2)
    discount_type = models.SmallIntegerField(choices=Discount.Types.choices())
    optional = models.BooleanField(default=False)

    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)


class ReservationRefund(TimestampModel):
    """
    Refunds toward a Reservation
    """

    value = models.DecimalField(max_digits=8, decimal_places=2)
    description = models.CharField(max_length=200, blank=True, default="")
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, related_name="refunds")


class CheckInOut(models.Model):
    """Check in / out information."""

    check_in_from = HourField(default="", blank=True)  # empty means flexible hours
    check_in_to = HourField(default="", blank=True)  # empty means flexible hours
    check_out_until = HourField(default="", blank=True)  # empty means flexible hours
    place = models.CharField(max_length=20, default="", blank=True)
    booking_settings = models.OneToOneField(
        BookingSettings,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="check_in_out",
    )


# Information-related models


class PointOfInterest(models.Model):
    """Location that someone may find useful or interesting."""

    name = models.CharField(max_length=200)
    category = models.CharField(max_length=200, default="")
    description = models.TextField(default="", blank=True)
    address = models.TextField(default="", blank=True)
    coordinates = models.ForeignKey("Coordinates", null=True, on_delete=models.SET_NULL)
    image = models.ImageField(upload_to=UploadImageTo("pois"), null=True, blank=True)
    prop = models.ForeignKey("Property", on_delete=models.CASCADE, related_name="poi_set")
    url = models.URLField(blank=True, null=True, max_length=255)


class Image(TimestampModel):
    """
    Image of a property.

    Can preserves ordering up to ORDER_MAX elements.
    """

    ORDER_MAX = 1000

    url = models.ImageField(upload_to=UploadImageTo("properties/images"), max_length=500)
    thumbnail = models.ImageField(
        upload_to=UploadImageTo("properties/images/thumbnail"), max_length=500, null=True
    )
    caption = models.TextField(blank=True, default="")
    order = models.PositiveSmallIntegerField(
        blank=True, default=ORDER_MAX, validators=[MaxValueValidator(ORDER_MAX)]
    )

    prop = models.ForeignKey("Property", on_delete=models.CASCADE)

    external_id = models.CharField(max_length=100, blank=True, default="", null=True)

    objects = querysets.HostedQuerySet.as_manager()

    class Meta:
        ordering = ["order"]

    def generate_thumbnail(self):
        try:
            image = PilImage.open(self.url)
        except FileNotFoundError:
            return

        thumbnail_width = 200

        w, h = image.size
        ratio = w / thumbnail_width
        image = image.resize((thumbnail_width, int(h / ratio)), PilImage.ANTIALIAS)

        filename, ext = os.path.splitext(os.path.basename(self.url.name))
        ext = (ext or "png").lower().strip(".")
        if ext == "jpg":
            ext = "jpeg"
        thumbnail = BytesIO()
        image.save(thumbnail, ext)
        self.thumbnail.save(f"thumb_{filename}.{ext}", thumbnail, save=True)


class Video(TimestampModel):
    """
    Video of a property.

    Can preserves ordering up to ORDER_MAX elements.
    """

    ORDER_MAX = 1000

    url = models.FileField(
        upload_to=UploadImageTo("properties/videos"),
        max_length=500,
        validators=[
            FileExtensionValidator(
                ["3gp", "avi", "mov", "mp4", "mkv", "ogv", "ogm", "ogg", "oga", "webm"]
            )
        ],
    )
    caption = models.TextField(blank=True, default="")
    external_id = models.CharField(max_length=255, blank=True, default="")
    order = models.PositiveSmallIntegerField(
        blank=True, default=ORDER_MAX, validators=[MaxValueValidator(ORDER_MAX)]
    )
    prop = models.ForeignKey("Property", on_delete=models.CASCADE)

    objects = querysets.HostedQuerySet.as_manager()

    class Meta:
        ordering = ["order"]


class Room(models.Model):
    """A distinguishable space within a property."""

    class Types(choices.StrChoicesEnum):
        Attic = "AT"
        Basement = "BM"
        Bathroom = "BA"
        Bedroom = "BE"
        Common = "CM"
        Kids_Bedroom = "KB"
        Guest_Bedroom = "GB"
        Loft = "LO"
        Master_Bedroom = "MB"
        Other = "OT"

    class Beds(choices.StrChoicesEnum):
        King = "KS"
        Queen = "QS"
        Double = "DB"
        Single = "SS"
        Sofa = "SB"
        Couch = "CO"
        Air_Mattress = "AM"
        Bunk = "BB"
        Floor_Mattress = "FM"
        Toddler = "TB"
        Crib = "CR"
        Water = "WB"
        Hammock = "HA"

        # Not supported by Airbnb
        Twin = "TB"
        Other = "OT"
        No_Bed = "NB"

    description = models.CharField(max_length=200, default="", blank=True)
    room_type = models.CharField(
        max_length=2, choices=Types.choices(), default=Types.Other.value, blank=True
    )
    beds = ArrayField(
        models.CharField(max_length=2, choices=Beds.choices()), default=list, blank=True
    )
    bathrooms = models.IntegerField(default=0, blank=True)
    prop = models.ForeignKey("Property", on_delete=models.CASCADE)
    features = models.ManyToManyField("Feature", blank=True)


class BasicAmenities(models.Model):
    """Common things that are intended to make a more pleasant stay."""

    # Deprecated
    laundry = FalseBooleanField()
    internet = FalseBooleanField()
    parking = FalseBooleanField()
    car_rental = FalseBooleanField()
    free_breakfast = FalseBooleanField()
    room_service = FalseBooleanField()
    cooling = FalseBooleanField()
    hot_tub = FalseBooleanField()
    airport_shuttle = FalseBooleanField()
    wheelchair = FalseBooleanField()

    # Other
    hardwood_flooring = FalseBooleanField()
    furnished = FalseBooleanField()
    gated = FalseBooleanField()

    # Pets description
    dogs_allowed = FalseBooleanField()
    cats_allowed = FalseBooleanField()
    large_dogs_allowed = FalseBooleanField()

    # Common
    essentials = FalseBooleanField()
    kitchen = FalseBooleanField()
    ac = FalseBooleanField()
    heating = FalseBooleanField()
    hair_dryer = FalseBooleanField()
    hangers = FalseBooleanField()
    iron = FalseBooleanField()
    washer = FalseBooleanField()
    dryer = FalseBooleanField()
    hot_water = FalseBooleanField()
    laundry_type = models.CharField(
        choices=LaundryType.choices(), max_length=3, blank=True, default=LaundryType.none
    )
    tv = FalseBooleanField()
    cable = FalseBooleanField()
    fireplace = FalseBooleanField()
    private_entrance = FalseBooleanField()
    private_living_room = FalseBooleanField()
    lock_on_bedroom_door = FalseBooleanField()
    shampoo = FalseBooleanField()
    bed_linens = FalseBooleanField()
    extra_pillows_and_blankets = FalseBooleanField()
    wireless_internet = FalseBooleanField()
    ethernet_connection = FalseBooleanField()
    pocket_wifi = FalseBooleanField()
    laptop_friendly = FalseBooleanField()

    # Kitchen
    microwave = FalseBooleanField()
    coffee_maker = FalseBooleanField()
    refrigerator = FalseBooleanField()
    dishwasher = FalseBooleanField()
    dishes_and_silverware = FalseBooleanField()
    cooking_basics = FalseBooleanField()
    oven = FalseBooleanField()
    stove = FalseBooleanField()

    # Facility
    # On street vs off street parking available
    # deprecated free_parking
    free_parking = FalseBooleanField()
    street_parking = FalseBooleanField()
    # Main parking type
    parking_type = models.CharField(
        choices=ParkingType.choices(), max_length=3, blank=True, default=ParkingType.none
    )
    # Free or paid parking
    paid_parking = FalseBooleanField()
    # Optional rental parking fee
    parking_fee = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True, default=None
    )

    # Optional parking description
    parking_description = models.TextField(blank=True)
    paid_parking_on_premises = FalseBooleanField()

    ev_charger = FalseBooleanField()
    gym = FalseBooleanField()
    pool = FalseBooleanField()
    jacuzzi = FalseBooleanField()
    single_level_home = FalseBooleanField()

    # Outdoor
    bbq_area = FalseBooleanField()
    patio_or_balcony = FalseBooleanField()
    garden_or_backyard = FalseBooleanField()

    # Special
    breakfast = FalseBooleanField()
    beach_essentials = FalseBooleanField()

    # Logistics
    luggage_dropoff_allowed = FalseBooleanField()
    long_term_stays_allowed = FalseBooleanField()
    cleaning_before_checkout = FalseBooleanField()

    # Home Safety
    fire_extinguisher = FalseBooleanField()
    carbon_monoxide_detector = FalseBooleanField()
    smoke_detector = FalseBooleanField()
    first_aid_kit = FalseBooleanField()

    # Location
    beachfront = FalseBooleanField()
    lake_access = FalseBooleanField()
    ski_in_ski_out = FalseBooleanField()
    waterfront = FalseBooleanField()

    # Family
    baby_bath = FalseBooleanField()
    baby_monitor = FalseBooleanField()
    babysitter_recommendations = FalseBooleanField()
    bathtub = FalseBooleanField()
    changing_table = FalseBooleanField()
    childrens_books_and_toys = FalseBooleanField()
    childrens_dinnerware = FalseBooleanField()
    crib = FalseBooleanField()
    fireplace_guards = FalseBooleanField()
    game_console = FalseBooleanField()
    high_chair = FalseBooleanField()
    outlet_covers = FalseBooleanField()
    pack_n_play_travel_crib = FalseBooleanField()
    room_darkening_shades = FalseBooleanField()
    stair_gates = FalseBooleanField()
    table_corner_guards = FalseBooleanField()
    window_guards = FalseBooleanField()

    # Accessibility Inside Home
    wide_hallway_clearance = FalseBooleanField()

    # Accessibility Getting Home
    home_step_free_access = FalseBooleanField()
    elevator = FalseBooleanField()
    path_to_entrance_lit_at_night = FalseBooleanField()
    home_wide_doorway = FalseBooleanField()
    flat_smooth_pathway_to_front_door = FalseBooleanField()
    disabled_parking_spot = FalseBooleanField()

    # Accessibility Bedroom
    bedroom_step_free_access = FalseBooleanField()
    wide_clearance_to_bed = FalseBooleanField()
    bedroom_wide_doorway = FalseBooleanField()
    accessible_height_bed = FalseBooleanField()
    electric_profiling_bed = FalseBooleanField()

    # Accessibility Bathroom
    bathroom_step_free_access = FalseBooleanField()
    grab_rails_in_shower = FalseBooleanField()
    grab_rails_in_toilet = FalseBooleanField()
    accessible_height_toilet = FalseBooleanField()
    rollin_shower = FalseBooleanField()
    shower_chair = FalseBooleanField()
    bathroom_wide_doorway = FalseBooleanField()
    tub_with_shower_bench = FalseBooleanField()
    wide_clearance_to_shower_and_toilet = FalseBooleanField()
    handheld_shower_head = FalseBooleanField()

    # Accessibility Common Areas
    common_space_step_free_access = FalseBooleanField()
    common_space_wide_doorway = FalseBooleanField()

    # Accessibility Equipment
    mobile_hoist = FalseBooleanField()
    pool_hoist = FalseBooleanField()
    ceiling_hoist = FalseBooleanField()

    wifi_ssid = models.CharField(max_length=64, blank=True, default="")
    wifi_password = models.CharField(max_length=64, blank=True, default="")

    prop = models.OneToOneField(
        "Property", related_name="basic_amenities", on_delete=models.CASCADE
    )


class AdvancedAmenities(models.Model):
    wifi_ssid = models.CharField(max_length=64, blank=True, default="")
    wifi_password = models.CharField(max_length=64, blank=True, default="")
    # early_bag_dropoff_allowed = FalseBooleanField()
    # late_check_out_allowed = FalseBooleanField()
    # early_check_in_allowed = FalseBooleanField()


class Feature(models.Model):
    """Something that is intended to make a more pleasant stay."""

    class Categories(choices.IntChoicesEnum):
        No_Category = 0
        Safety = 1
        Rules = 2
        Amenity_Kitchen = 3
        Amenity = 4
        Activities = 5
        Views = 6
        Access = 7
        Area = 8

    name = models.CharField(max_length=200)
    override = models.CharField(max_length=200, default="")
    display = FalseBooleanField()
    value = models.IntegerField(default=1, blank=True)  # Deprecated
    category = models.IntegerField(
        null=True, default=Categories.No_Category.value, choices=Categories.choices()
    )
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True)

    class Meta:
        indexes = [BrinIndex(fields=["name"])]

    @property
    def is_supported(self):
        return self.organization_id is None


class Availability(BaseAvailability):
    time_frame = DateRangeField(null=True, default=(None, None))
    prop = models.ForeignKey("Property", on_delete=models.CASCADE, null=True)

    default_manager = models.Manager()
    objects = ProductionManager(lookup_field="prop__is_sandbox")

    @classmethod
    def get_visit_availability(cls, start_date, end_date, prop_id):
        return (
            cls.objects.filter(prop_id=prop_id, time_frame__overlap=(start_date, end_date))
            .exclude(time_frame=(None, None))
            .order_by("-time_frame")
        )

    @classmethod
    def availability_per_day(cls, start_date, end_date, prop_id):
        """
        Return days mapped on Availability

        `start_date` is inclusive, `end_date` is exclusive. Raises `ValueError`
        if missing data for any day in a period.
        """
        visit_availability = cls.get_visit_availability(start_date, end_date, prop_id)

        try:
            default_availability = AvailabilitySettings.objects.get(prop=prop_id)
        except AvailabilitySettings.DoesNotExist:
            default_availability = None

        availability = dict.fromkeys(date_range(start_date, end_date), default_availability)

        for va in visit_availability:
            availability_range = date_range(
                max(start_date, va.time_frame.lower or date.min),
                min(end_date, va.time_frame.upper or date.max),
            )

            availability.update({visit_day: va for visit_day in availability_range})

        return availability


class Building(models.Model):
    """A recognizable building."""

    name = models.CharField(max_length=50)


class Owner(models.Model):
    """Contact data to an owner of a property."""

    first_name = models.CharField(max_length=20, blank=True)
    last_name = models.CharField(max_length=40, blank=True)
    company_name = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = PhoneField(blank=True)


class Location(models.Model):
    """Administrative location of a property."""

    continent = models.CharField(max_length=35, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="")
    country_code = models.CharField(
        max_length=2, blank=True, default="", choices=choices.CountryCode.choices()
    )
    region = models.CharField(max_length=100, blank=True, default="")
    state = models.CharField(max_length=100, blank=True, default="")
    city = models.CharField(max_length=100, default="", blank=True)
    address = models.CharField(max_length=150, default="", blank=True)
    apartment = models.CharField(max_length=150, default="", blank=True)
    postal_code = models.CharField(max_length=8, default="", blank=True)
    longitude = models.DecimalField(max_digits=15, decimal_places=12, null=True, blank=True)
    latitude = models.DecimalField(max_digits=15, decimal_places=12, null=True, blank=True)


class ArrivalInstruction(models.Model):
    """Information to help Customer get to a property."""

    landlord = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    phone = PhoneField(blank=True)
    description = models.TextField(blank=True)
    contact_days_before_arrival = models.IntegerField(null=True, blank=True)
    pick_up_description = models.CharField(max_length=500, blank=True)

    def __str__(self):
        return self.description


class Coordinates(models.Model):
    """GPS coordinates."""

    longitude = models.DecimalField(max_digits=15, decimal_places=12)
    latitude = models.DecimalField(max_digits=15, decimal_places=12)


class HouseRules(models.Model):
    """House rules."""

    description = models.TextField()
    prop = models.ForeignKey("Property", on_delete=models.CASCADE)


class Suitability(models.Model):
    """Suitability."""

    class SuitabilityProvided(choices.StrChoicesEnum):
        Yes = "YES"
        No = "NO"
        Unknown = "UN"
        Inquire = "Inq"

    elderly = models.CharField(
        max_length=3,
        choices=SuitabilityProvided.choices(),
        default=SuitabilityProvided.Unknown.value,
    )
    pets = models.CharField(
        max_length=3,
        choices=SuitabilityProvided.choices(),
        default=SuitabilityProvided.Unknown.value,
    )
    kids = models.CharField(
        max_length=3,
        choices=SuitabilityProvided.choices(),
        default=SuitabilityProvided.Unknown.value,
    )
    large_groups = models.CharField(
        max_length=3,
        choices=SuitabilityProvided.choices(),
        default=SuitabilityProvided.Unknown.value,
    )
    events = models.CharField(
        max_length=3,
        choices=SuitabilityProvided.choices(),
        default=SuitabilityProvided.Unknown.value,
    )
    smoking = models.CharField(
        max_length=3,
        choices=SuitabilityProvided.choices(),
        default=SuitabilityProvided.Unknown.value,
    )
    handicap = models.CharField(
        max_length=3,
        choices=SuitabilityProvided.choices(),
        default=SuitabilityProvided.Unknown.value,
    )
    infants = models.CharField(
        max_length=3,
        choices=SuitabilityProvided.choices(),
        default=SuitabilityProvided.Unknown.value,
    )
    children_not_allowed_details = models.TextField(null=True, blank=True, default="")
    prop = models.OneToOneField("Property", related_name="suitability", on_delete=models.CASCADE)


class Blocking(TimestampModel):
    """Block certain date range from being reserved"""

    time_frame = DateRangeField()
    summary = models.TextField(default="", blank=True, max_length=1000)
    prop = models.ForeignKey("Property", on_delete=models.CASCADE)

    default_manager = models.Manager()
    objects = ProductionManager(lookup_field="prop__is_sandbox")

    def to_ical(self):
        start_date = self.time_frame.lower
        end_date = self.time_frame.upper - timedelta(days=1)
        return icalendar.Event(
            {
                "SUMMARY": "Event - Voyajoy Blocking",
                "DTSTART;VALUE=DATE": get_ical_friendly_date(start_date),
                "DTEND;VALUE=DATE": get_ical_friendly_date(end_date),
                "DTSTAMP;VALUE=DATE-TIME": start_date.isoformat(),
                "UID": "{}@voyajoy.com".format(
                    md5(
                        ":".join(
                            [start_date.isoformat(), end_date.isoformat(), str(self.prop_id)]
                        ).encode()
                    ).hexdigest()
                ),
            }
        )


class TurnDay(TimestampModel):
    """TurnDay describes seasonal minimum stay length requirements."""

    time_frame = DateRangeField()
    days = ArrayField(
        models.PositiveSmallIntegerField(choices=choices.WeekDays.choices()),
        default=list,
        blank=True,
    )
    prop = models.ForeignKey("Property", on_delete=models.CASCADE)


class SchedulingAssistant(TimestampModel):
    automatically_assign = models.BooleanField(default=False, blank=False)
    cleaning_from_time = models.TimeField(blank=True, null=True)
    cleaning_to_time = models.TimeField(blank=True, null=True)
    prop = models.OneToOneField(
        "Property", on_delete=models.CASCADE, related_name="scheduling_assistant"
    )
    time_estimate = models.DurationField(blank=True, default=timedelta(minutes=60))
    default_cost = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True, default=None
    )
    enabled = FalseBooleanField()


class ReservationNote(TimestampModel):
    body = models.TextField(default="", blank=True)
    author = models.ForeignKey(User, related_name="+", on_delete=models.CASCADE)
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)

    class Meta:
        permissions = (("view_reservationnote", "Can view reservation notes"),)


class SyncLog(models.Model):
    status = models.PositiveSmallIntegerField(choices=choices.SyncStatus.choices())
    prop = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="sync_logs")
    date_created = models.DateTimeField(auto_now_add=True)


class GroupUserAssignment(TimestampModel):
    user = models.ForeignKey(
        get_user_model(), on_delete=models.CASCADE, related_name="group_user_assignments"
    )
    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, related_name="group_user_assignments"
    )


class ExternalListing(models.Model):
    class Sources(choices.IntChoicesEnum):
        Airbnb = auto()
        VRBO = auto()
        Booking = auto()
        Tripadvisor = auto()
        Other = auto()

    prop = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="external_listings")
    url = models.URLField()
    source = models.PositiveSmallIntegerField(choices=Sources.choices())
    listing_id = models.CharField(max_length=64)

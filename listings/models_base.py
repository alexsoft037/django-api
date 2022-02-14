from django.contrib.postgres.fields import ArrayField, HStoreField
from django.db import models

from cozmo_common.db.models import TimestampModel
from . import choices


class BaseAvailability(TimestampModel):
    """Conditions which must be met to make a reservation."""

    min_stay = models.PositiveSmallIntegerField(default=1)  # Default min nights
    max_stay = models.PositiveSmallIntegerField(null=True, default=None)  # Default max nights
    preparation = models.PositiveSmallIntegerField(null=True, default=None)  # Turn over days
    advance_notice = models.PositiveSmallIntegerField(null=True, default=None)  # Booking lead time
    check_in_days = ArrayField(
        models.PositiveSmallIntegerField(choices=choices.WeekDays.choices()),
        default=list,
        blank=True,
    )
    check_out_days = ArrayField(
        models.PositiveSmallIntegerField(choices=choices.WeekDays.choices()),
        default=list,
        blank=True,
    )
    days_min_nights = HStoreField(default={})
    min_age = models.PositiveSmallIntegerField(null=True, default=None)
    booking_window_months = models.PositiveSmallIntegerField(default=6)
    """Rolling window of time in months that allows the property to be booked """

    class Meta:
        abstract = True


class BaseFee(models.Model):

    TaxTypes = choices.TaxTypes
    FeeTypes = choices.FeeTypes

    FEE_TAX_TYPES = TaxTypes.choices() + FeeTypes.choices()

    name = models.CharField(max_length=200, blank=True, default="")
    value = models.DecimalField(max_digits=8, decimal_places=2)
    fee_tax_type = models.CharField(
        max_length=3, choices=FEE_TAX_TYPES, default=FeeTypes.Other_Fee.value
    )
    description = models.CharField(max_length=200, blank=True, default="")
    is_percentage = models.BooleanField(default=False)
    optional = models.BooleanField(default=False)
    taxable = models.BooleanField(default=False)
    refundable = models.BooleanField(default=False, blank=True)

    class Meta:
        abstract = True


class BasePricingSettings(TimestampModel):

    currency = models.CharField(
        max_length=3, choices=choices.Currencies.choices(), default=choices.Currencies.USD.value
    )
    nightly = models.DecimalField(max_digits=9, decimal_places=2)
    weekend = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)

    weekly = models.DecimalField(max_digits=9, decimal_places=2, blank=True, default=0)
    monthly = models.DecimalField(max_digits=9, decimal_places=2, blank=True, default=0)

    cleaning_fee = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
    extra_person_fee = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
    security_deposit = models.DecimalField(max_digits=9, decimal_places=2, blank=True, null=True)
    # TODO add price factors

    class Meta:
        abstract = True


class BaseDiscount(models.Model):
    class Types(choices.IntChoicesEnum):
        Early_Bird = 1
        Late_Bird = 2

    value = models.DecimalField(max_digits=8, decimal_places=2)
    discount_type = models.SmallIntegerField(choices=Types.choices())
    optional = models.BooleanField(default=False)

    class Meta:
        abstract = True

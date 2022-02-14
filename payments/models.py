from enum import auto

from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import JSONField
from django.db import models

from accounts.models import Organization
from cozmo_common.enums import ChoicesEnum, IntChoicesEnum, StrChoicesEnum
from listings.choices import Currencies
from payments.choices import PlanType


class CreditCard(models.Model):
    class CardBrand(IntChoicesEnum):
        Visa = auto()
        American_Express = auto()
        MasterCard = auto()
        Discover = auto()
        JCB = auto()
        Diners_Club = auto()
        Unknown = auto()

    external_id = models.CharField(max_length=150, default="")
    last4 = models.CharField(max_length=4, default="")
    brand = models.PositiveSmallIntegerField(
        choices=CardBrand.choices(), default=CardBrand.Unknown.value
    )
    exp_year = models.PositiveSmallIntegerField(null=True)
    exp_month = models.PositiveSmallIntegerField(null=True)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True)
    customer_obj_id = models.PositiveIntegerField(null=True)
    customer_obj = GenericForeignKey("content_type", "customer_obj_id")

    date_updated = models.DateTimeField(auto_now=True, null=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)


class Customer(models.Model):

    external_id = models.CharField(max_length=150)
    organization = models.OneToOneField("accounts.Organization", on_delete=models.CASCADE)
    credit_cards = GenericRelation(
        CreditCard,
        related_query_name="customer",
        content_type_field="content_type",
        object_id_field="customer_obj_id",
    )


class PricingPlan(models.Model):
    class Intervals(ChoicesEnum):
        monthly = "month"
        yearly = "year"

    alias = models.CharField(max_length=100, help_text="External service nick name")
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    currency = models.CharField(
        choices=Currencies.choices(), default=Currencies.USD.value, max_length=3
    )
    interval = models.CharField(
        choices=Intervals.choices(), default=Intervals.monthly.value, max_length=10
    )
    external_id = models.CharField(max_length=150, default="")
    tier = models.ForeignKey("ProductTier", on_delete=models.CASCADE)

    interval_count = 1


class ProductTier(models.Model):

    name = models.CharField(max_length=100, help_text="Name displayable to users")
    external_id = models.CharField(max_length=150)

    type = "service"

    @property
    def statement_descriptor(self):
        return f"Voyajoy {self.name} tier"


class Coupon(models.Model):
    class DurationType(StrChoicesEnum):
        Forever = "forever"
        Once = "once"
        Repeating = "repeating"

    external_id = models.CharField(max_length=200)
    name = models.CharField(max_length=40, null=True, blank=True)
    percent_off = models.DecimalField(decimal_places=2, max_digits=4, null=True, blank=True)
    amount_off = models.PositiveIntegerField(null=True, blank=True)
    currency = models.CharField(
        choices=Currencies.choices(),
        default=Currencies.USD.value,
        max_length=3,
        null=True,
        blank=True,
    )
    duration = models.CharField(max_length=15, choices=DurationType.choices())
    duration_in_months = models.PositiveSmallIntegerField(null=True, blank=True)
    max_redemptions = models.PositiveSmallIntegerField(null=True, blank=True)
    redeem_by = models.DateTimeField(null=True, blank=True)
    is_valid = models.BooleanField(default=True)


class Subscription(models.Model):
    """
    Subscription should have an active/not active status
    Organization, if none, has no subscription
    Fee is total amount
    Tied to a pricing plan (v2)
    """
    # pricing_plan = models.ForeignKey(PricingPlan, on_delete=models.CASCADE, null=True)
    is_active = models.BooleanField(default=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="subscription", null=True
    )
    plan = models.PositiveSmallIntegerField(choices=PlanType.choices(), null=True)
    external_id = models.CharField(max_length=150)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True)

    @property
    def price_total(self):
        return None

    class Meta:
        permissions = (("view_subscription", "Can view subscriptions"),)


class Charge(models.Model):
    """
    Charges are tied to reservations and to org
    """

    class Status(IntChoicesEnum):
        Succeeded = auto()
        Pending = auto()
        Failed = auto()
        Delayed = auto()

    class Schedule(IntChoicesEnum):
        Now = auto()
        Custom = auto()
        Specific_Date = auto()
        At_time_of_check_in = auto()
        At_time_of_booking = auto()

    external_id = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    refunded_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0, blank=True)
    is_refundable = models.BooleanField(default=False, blank=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    payment_for_id = models.PositiveIntegerField()
    payment_for = GenericForeignKey("content_type", "payment_for_id")
    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE)
    status = models.PositiveIntegerField(
        choices=Status.choices(), null=True, blank=False, default=Status.Delayed.value
    )
    source_id = models.CharField(max_length=150, default="")  # Stripe source_id
    schedule = models.PositiveSmallIntegerField(choices=Schedule.choices(), null=True, blank=False)
    schedule_value = models.DateField(null=True, blank=True)
    card = models.ForeignKey(CreditCard, on_delete=models.SET_NULL, null=True, blank=True)

    date_updated = models.DateTimeField(auto_now=True, null=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["external_id"])]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        watched_fields = ("amount", "refunded_amount")
        self._initial_data = {field: self.__dict__[field] for field in watched_fields}

    def _changed_fields(self):
        return {
            field: value
            for field, value in self._initial_data.items()
            if value != self.__dict__[field]
        }

    @property
    def name(self):
        return f"Payment for {self.payment_for.__class__.__name__} {self.payment_for_id}"


class Dispute(models.Model):
    external_id = models.CharField(max_length=150)
    charge = models.ForeignKey(Charge, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    balance_transaction = models.CharField(max_length=150, default="", blank=True)
    status = models.CharField(max_length=50)
    reason = models.CharField(max_length=50)
    livemode = models.BooleanField(default=False)
    is_charge_refundable = models.BooleanField(default=False)
    currency = models.CharField(
        max_length=50, choices=Currencies.choices(), default=Currencies.USD.value
    )
    created = models.PositiveIntegerField()

    metadata = JSONField(null=True, blank=True)
    evidence = JSONField(null=True, blank=True)
    evidence_details = JSONField(null=True, blank=True)
    balance_transactions = JSONField(null=True, blank=True)

    date_updated = models.DateTimeField(auto_now=True, null=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)


class PlaidApp(models.Model):

    name = models.CharField(max_length=100, default="", help_text="User-friendly name")
    item_id = models.CharField(max_length=100)
    access_token = models.CharField(max_length=100)
    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE)


class PlaidTransaction(models.Model):
    transaction_id = models.CharField(max_length=100)
    value = models.DecimalField(max_digits=8, decimal_places=2)
    title = models.CharField(max_length=250)
    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE)

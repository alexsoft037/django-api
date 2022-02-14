from datetime import datetime
from decimal import Decimal

from django.conf import settings
from rest_framework import serializers
from rest_framework.fields import (
    BooleanField,
    CharField,
    IntegerField,
    SerializerMethodField,
    URLField,
)
from stripe.error import CardError, InvalidRequestError, StripeError

from cozmo_common.fields import (
    ChoicesField,
    DefaultOrganization,
    EpochTimestampField,
    IntegerMoneyField,
    ModelChoicesField,
    NestedRelatedField,
    PositiveSmallIntegerChoicesField,
)
from cozmo_common.serializers import ValueFormattedSerializer
from cozmo_common.utils import format_decimal_to_str, get_dt_from_timestamp
from crm.models import Contact
from crm.serializers import ContactSerializer
from listings.models import Reservation
from payments.choices import PlanType
from . import models
from .exceptions import PaymentError
from .services import Plaid, Stripe


class GenericCreditCardSerializer(serializers.ModelSerializer):
    serializer_choice_field = ChoicesField

    class Meta:
        model = models.CreditCard
        fields = ("last4", "brand", "exp_year", "exp_month")


class ChargeSerializer(ValueFormattedSerializer):
    serializer_choice_field = PositiveSmallIntegerChoicesField

    payment_for = ModelChoicesField(choices=((Reservation, "Reservation"),))
    organization = serializers.HiddenField(default=DefaultOrganization())
    card = NestedRelatedField(
        serializer=GenericCreditCardSerializer, queryset=models.CreditCard.objects.all()
    )

    class Meta:
        model = models.Charge
        fields = (
            "id",
            "status",
            "external_id",
            "payment_for_id",
            "payment_for",
            "value",
            "refunded_value",
            "is_refundable",
            "organization",
            "schedule",
            "schedule_value",
            "card",
        )
        read_only_fields = ("external_id", "refunded_amount", "status")
        extra_kwargs = {
            "value": {"source": "amount"},
            "refunded_value": {"source": "refunded_amount"},
        }

    def validate(self, data):
        organization = data["organization"]
        PaymentFor = data.pop("payment_for")

        stripe_app = organization.stripeapp_set.first()
        if not stripe_app:
            raise serializers.ValidationError("User needs to add Stripe to his installed apps")

        if not PaymentFor.objects.filter(
            prop__organization=organization, pk=data["payment_for_id"]
        ).exists():
            raise serializers.ValidationError({"payment_for_id": "Not found"})
        else:
            data["content_type"] = models.ContentType.objects.get_for_model(PaymentFor)

        validated_data = super().validate(data)

        if data["schedule"] == self.Meta.model.Schedule.Now.pretty_name:
            try:
                stripe = Stripe()
                charge = stripe.charge(
                    stripe_app.stripe_user_id,
                    int(data["amount"] * 100),
                    validated_data.get("card").external_id,
                )
                data["external_id"] = charge.id
                data["status"] = self.Meta.model.Status[charge.status]
            except PaymentError as e:
                raise serializers.ValidationError({"token": ". ".join(e.args)})

        return data


class ChargeRefundSerializer(serializers.ModelSerializer):
    payment_for = ModelChoicesField(choices=((Reservation, "Reservation"),), read_only=True)
    to_refund = serializers.DecimalField(
        max_digits=8, decimal_places=2, min_value=Decimal("0.01"), write_only=True
    )

    class Meta:
        model = models.Charge
        fields = (
            "id",
            "external_id",
            "payment_for_id",
            "payment_for",
            "amount",
            "refunded_amount",
            "is_refundable",
            "to_refund",
        )
        read_only_fields = (
            "id",
            "external_id",
            "payment_for_id",
            "payment_for",
            "amount",
            "refunded_amount",
            "is_refundable",
        )

    def validate_to_refund(self, to_refund):
        if self.instance is None:
            raise serializers.ValidationError("Cannot refund unknown charge")
        elif to_refund > (self.instance.amount - self.instance.refunded_amount):
            raise serializers.ValidationError("Maximal refund amount exceeded")
        elif self.instance.status != models.Charge.Status.Succeeded:
            raise serializers.ValidationError("Cannot refund not succeeded charge")

        Stripe().refund(self.instance.external_id, int(to_refund * 100))
        return to_refund

    def update(self, instance, data):
        instance.refunded_amount += data["to_refund"]
        instance.save()
        return instance


class BaseCreditCardSerializer(serializers.ModelSerializer):
    token = serializers.CharField(write_only=True)
    serializer_choice_field = ChoicesField

    def delete(self):
        stripe = Stripe()
        customer_id = self.instance.customer_obj.external_id
        stripe.remove_card(customer_id, self.instance.external_id)
        self.instance.delete()

    def _get_data(self, card, customer):
        return {
            "last4": card.last4,
            "external_id": card.id,
            "customer_obj": customer,
            "brand": models.CreditCard.CardBrand[card.brand],
            "exp_year": card.exp_year,
            "exp_month": card.exp_month,
        }

    def _get_customer(self, validated_data, stripe):
        raise NotImplementedError

    def create(self, validated_data):
        stripe = Stripe()
        cozmo_customer = self._get_customer(validated_data, stripe)

        try:
            card = stripe.add_card(cozmo_customer.external_id, validated_data.pop("token"))
        except (InvalidRequestError, CardError) as e:
            raise serializers.ValidationError(e.json_body.get("error", {}).get("message"))
        validated_data = self._get_data(card, cozmo_customer)
        return super().create(validated_data)


class CreditCardSerializer(BaseCreditCardSerializer):
    organization = serializers.HiddenField(default=DefaultOrganization())

    class Meta:
        model = models.CreditCard
        fields = ("last4", "brand", "exp_year", "exp_month", "organization", "token")
        read_only_fields = ("last4", "brand", "exp_year", "exp_month")

    def _get_customer(self, validated_data, stripe):
        organization = validated_data.get("organization")
        try:
            cozmo_customer = organization.customer
        except models.Customer.DoesNotExist:
            customer = stripe.create_customer()

            cozmo_customer = models.Customer.objects.create(
                external_id=customer.id, organization=organization
            )
        return cozmo_customer

    def create(self, validated_data):
        customer = self._get_customer(validated_data, Stripe())
        cards = customer.credit_cards.all()
        for card in cards:
            CreditCardSerializer(instance=card).delete()
        return super().create(validated_data)


class SubscriptionCreditCardSerializer(CreditCardSerializer):
    name = CharField(required=False)
    address_line1 = CharField(required=False)
    address_line2 = CharField(allow_blank=True, required=False)
    city = CharField(required=False)
    zipcode = CharField(required=False)
    state = CharField(required=False)

    class Meta(CreditCardSerializer.Meta):
        fields = CreditCardSerializer.Meta.fields + (
            "name",
            "address_line1",
            "address_line2",
            "city",
            "zipcode",
            "state",
        )
        extra_kwargs = {
            "name": {"write_only": True},
            "address_line1": {"write_only": True},
            "address_line2": {"write_only": True},
            "city": {"write_only": True},
            "zipcode": {"write_only": True},
            "state": {"write_only": True},
        }

    def create(self, validated_data):
        data = {
            "name": validated_data.pop("name"),
            "address_line1": validated_data.pop("address_line1"),
            "address_line2": validated_data.pop("address_line2", ""),
            "address_city": validated_data.pop("city"),
            "address_zip": validated_data.pop("zipcode"),
            "address_state": validated_data.pop("state"),
        }
        instance = super().create(validated_data)

        stripe = Stripe()
        cozmo_customer = self._get_customer(validated_data, stripe)
        try:
            stripe.modify_card(cozmo_customer.external_id, instance.external_id, data)
        except (InvalidRequestError, CardError) as e:
            raise serializers.ValidationError(e.json_body.get("error", {}).get("message"))
        # validated_data = self._get_data(card, cozmo_customer)
        return instance


class GuestCreditCardSerializer(BaseCreditCardSerializer):
    token = serializers.CharField(write_only=True)
    customer = NestedRelatedField(
        queryset=Contact.objects.all(),
        serializer=ContactSerializer,
        required=False,
        source="customer_obj",
    )
    customer_email = serializers.EmailField(required=False)
    organization = serializers.HiddenField(default=DefaultOrganization())

    class Meta:
        model = models.CreditCard
        fields = (
            "id",
            "external_id",
            "last4",
            "brand",
            "exp_year",
            "exp_month",
            "token",
            "customer",
            "customer_email",
            "organization",
        )
        read_only_fields = ("last4", "external_id", "brand", "exp_year", "exp_month")

    def validate(self, data):
        if self.partial is False and "customer_obj" not in data and "customer_email" not in data:
            raise serializers.ValidationError("One of 'customer' or 'customer_email' is required")
        return data

    def validate_customer_email(self, customer_email):
        if not Contact.objects.filter(email=customer_email).exists():
            raise serializers.ValidationError("Does not exist")
        return customer_email

    def _get_customer(self, validated_data, stripe):
        cozmo_customer = validated_data.get("customer_obj", None)
        if cozmo_customer is None:
            cozmo_customer = Contact.objects.filter(
                organization=validated_data["organization"], email=validated_data["customer_email"]
            ).first()
        if not cozmo_customer.external_id:
            customer = stripe.create_customer()
            cozmo_customer.external_id = customer.id
            cozmo_customer.save()
        return cozmo_customer


class BillingHistorySerializer(serializers.Serializer):
    status = CharField()
    refunded = BooleanField()
    paid = BooleanField()
    description = CharField()
    amount = IntegerMoneyField()
    amount_refunded = IntegerMoneyField()
    created = EpochTimestampField()
    currency = CharField()
    failure_code = CharField()
    failure_message = CharField()
    receipt_url = URLField()


class BillingHistoryInvoiceSerializer(serializers.Serializer):
    amount = IntegerMoneyField(source="total")
    status = CharField()
    paid = BooleanField()
    description = SerializerMethodField()
    created = EpochTimestampField()
    currency = CharField()
    receipt_url = SerializerMethodField()

    def get_description(self, obj):
        return ", ".join([(d.plan.nickname or "") for d in obj.lines.data])

    def get_receipt_url(self, obj):
        stripe = Stripe()
        charge = obj.charge
        return stripe.retrieve_charge_receipt_url(charge) if charge else None


class SubscribeSerializer(serializers.ModelSerializer):
    organization = serializers.HiddenField(default=DefaultOrganization())
    payment_methods = GenericCreditCardSerializer(
        many=True, source="customer.credit_cards", read_only=True
    )
    plan = ChoicesField(choices=PlanType.choices(), allow_null=True, default=PlanType.base)

    class Meta:
        model = models.Subscription
        fields = ("id", "plan", "coupon_id", "organization", "payment_methods")

    # def validate_coupon_id(self, coupon_id):
    #     stripe = Stripe()
    #     try:
    #         coupon = stripe.retrieve_coupon(coupon_id)
    #     except InvalidRequestError as e:
    #         raise serializers.ValidationError(e.json_body.get("error", {}).get("message"))
    #
    #     if not coupon.valid:
    #         raise serializers.ValidationError(f"Coupon with {coupon_id} is not valid")
    #
    #     return coupon_id

    def validate(self, attrs):
        organization = attrs.get("organization")
        if organization.subscription.exists():
            raise serializers.ValidationError("Subscription already exists")
        return attrs

    def _get_customer(self, organization):
        stripe = Stripe()
        try:
            customer = organization.customer
        except models.Customer.DoesNotExist:
            customer = stripe.create_customer(name=organization.name, email=organization.email)

            customer = models.Customer.objects.create(
                external_id=customer.id, organization=organization
            )
        return customer

    def get_plan_config(self, plan_id):
        return settings.SUBSCRIPTION_PLANS[PlanType(plan_id).name]

    def create(self, validated_data):
        stripe = Stripe()
        organization = validated_data.get("organization")

        customer = self._get_customer(organization)
        plan = validated_data.get("plan", None)
        product = self.get_plan_config(plan)
        external_id = product["plan_id"]
        trial_period = product["trial_period_days"]
        # get plan id
        coupon_id = validated_data.get("coupon_id", None)

        subscribe_params = {
            "customer_id": customer.external_id,
            "plan_id": external_id,
            "coupon_id": coupon_id,
        }

        if trial_period:
            subscribe_params.update({"trial_period_days": trial_period})
        # if ApplicationTypes.iCal_Magic.value in organization.applications:
        #     subscribe_params.update({"trial_period_days": settings.ICALL_MAGIC_TRIAL_PERIOD})

        sub = stripe.subscribe(**subscribe_params)
        validated_data.update({"external_id": sub.id, "customer": customer, "is_active": True})
        return super().create(validated_data)

    def update(self, instance, validated_data):
        stripe = Stripe()

        plan = validated_data.get("plan", None)
        if plan:
            product = self.get_plan_config(plan)
            external_id = product["plan_id"]

            params = {"subscription_id": instance.external_id, "plan": external_id}

            stripe.update_subscription(**params)
        return super().update(instance, validated_data)

    def delete(self):
        stripe = Stripe()
        stripe.unsubscribe(self.instance.external_id)
        self.instance.delete()


class PricingPlanSerializer(serializers.ModelSerializer):
    serializer_choice_field = ChoicesField

    class Meta:
        model = models.PricingPlan
        fields = ("id", "amount", "currency", "interval")


class DisputeSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Dispute
        fields = "__all__"

    def to_internal_value(self, data):
        data = data.to_dict()
        charge_id = data.pop("charge")
        try:
            charge = models.Charge.objects.values("id").get(external_id=charge_id).get("id")
        except models.Charge.DoesNotExist:
            raise serializers.ValidationError({"charge": "Does not exist"})

        data["charge"] = charge
        data["external_id"] = data.pop("id")
        data["currency"] = data.pop("currency").upper()
        data["balance_transaction"] = data.pop("balance_transaction") or ""

        return super().to_internal_value(data)

    def create(self, validated_data):
        ModelClass = self.Meta.model
        instance = ModelClass.objects.filter(external_id=validated_data.get("external_id")).first()
        if instance:
            return super().update(instance, validated_data)
        else:
            return super().create(validated_data)


class CouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Coupon
        fields = "__all__"

    def to_internal_value(self, data):
        if data.get("id") and not data.get("external_id"):
            data["external_id"] = data.pop("id")

        if data.get("currency"):
            data["currency"] = data.pop("currency").upper()

        if data.get("redeem_by") and isinstance(data["redeem_by"], int):
            data["redeem_by"] = datetime.fromtimestamp(data["redeem_by"])

        if data.get("valid") is not None:
            data["is_valid"] = data.pop("valid")

        return super().to_internal_value(data)

    def validate_amount_off(self, amount_off):
        if amount_off is not None and amount_off < 1:
            raise serializers.ValidationError("must be greater than 0")
        return amount_off

    def validate_percent_off(self, percent_off):
        if percent_off is not None and not percent_off > 0:
            raise serializers.ValidationError("must be greater than 0")
        return percent_off

    def validate_max_redemptions(self, max_redemptions):
        if max_redemptions is not None and max_redemptions < 1:
            raise serializers.ValidationError("must be greater than 0")
        return max_redemptions

    def validate(self, data):
        percent_off = data.get("percent_off")
        amount_off = data.get("amount_off")
        duration = data.get("duration")

        if all([percent_off, amount_off]) or all([percent_off is None, amount_off is None]):
            raise serializers.ValidationError("Only one of percent_off, amount_off must be set")

        if duration == models.Coupon.DurationType.Repeating.value:
            duration_in_months = data.get("duration_in_months")
            if duration_in_months is None:
                raise serializers.ValidationError(
                    {"duration_in_months": f"must be set when duration is {duration}"}
                )

            if duration_in_months < 1:
                raise serializers.ValidationError({"duration_in_months": "must be greater than 0"})

        return data

    def create(self, validated_data):
        instance = models.Coupon.objects.filter(
            external_id=validated_data.get("external_id")
        ).first()
        if instance:
            return super().update(instance, validated_data)
        return super().create(validated_data)


class PlaidSerializer(serializers.ModelSerializer):
    public_token = serializers.CharField(write_only=True)
    organization = serializers.HiddenField(default=DefaultOrganization())

    class Meta:
        model = models.PlaidApp
        fields = ("id", "name", "public_token", "organization")

    def validate(self, data):
        response = Plaid.exchange(data.pop("public_token"))
        if "error" in response:
            raise serializers.ValidationError({"public_token": response["error"]})
        else:
            data["item_id"] = response["item_id"]
            data["access_token"] = response["access_token"]
        return data


class PlaidTransactionSerializer(serializers.ModelSerializer):
    organization = serializers.HiddenField(default=DefaultOrganization())

    class Meta:
        model = models.PlaidTransaction
        fields = ("id", "title", "value", "organization")


class MatchSerializer(serializers.ModelSerializer):
    organization = serializers.HiddenField(default=DefaultOrganization())

    class Meta:
        model = models.PlaidTransaction
        fields = ("id", "reservations", "organization")
        extra_kwargs = {"reservations": {"source": "reservation_set"}}


class BillingSubscriptionSerializer(serializers.Serializer):
    created = EpochTimestampField()
    trial_end = EpochTimestampField(allow_null=True)
    status = CharField()
    quantity = IntegerField()
    amount = IntegerMoneyField(source="plan.amount")
    currency = CharField(source="plan.currency")
    interval = CharField(source="plan.interval")
    interval_count = CharField(source="plan.interval_count")
    nickname = CharField(source="plan.nickname")
    next_bill = SerializerMethodField()
    active = BooleanField(source="plan.active")
    coupon = CharField(source="discount.coupon.id", allow_null=True)
    coupon_description = CharField(source="discount.coupon.name", allow_null=True)

    def get_next_bill(self, obj):
        stripe = Stripe()
        try:
            upcoming = stripe.retrieve_upcoming_invoice(obj.id)
            return {
                "amount": format_decimal_to_str(upcoming.total / 100),
                "date": get_dt_from_timestamp(upcoming.next_payment_attempt),
            }
        except StripeError:
            return None


class BillingSerializer(serializers.ModelSerializer):
    payment_methods = GenericCreditCardSerializer(many=True, source="customer.credit_cards")
    coupon_code = CharField(source="coupon.name", allow_null=True)
    plan = CharField(source="get_plan_display")
    history = SerializerMethodField()
    subscription = SerializerMethodField()

    class Meta:
        model = models.Subscription
        fields = ("is_active", "plan", "coupon_code", "payment_methods", "history", "subscription")

    def get_subscription(self, obj):
        stripe = Stripe()
        subscription = stripe.retrieve_subscription(sub_id=obj.external_id)
        serializer = BillingSubscriptionSerializer(instance=subscription)
        return serializer.data

    def get_history(self, obj):
        stripe = Stripe()
        # Filter out invoices that have been marked as paid, but have no charge ($0). These
        # invoices were most likely automatically created by stripe for subscription updates.
        charges = list(
            filter(
                lambda x: not (x.paid and not x.charge),
                stripe.list_invoices(customer_id=obj.customer.external_id),
            )
        )
        # charges = stripe.list_invoices(customer_id=obj.customer.external_id)
        # charges = stripe.list_charges(customer_id=obj.customer.external_id)
        # serializer = BillingHistorySerializer(instance=charges, many=True)
        serializer = BillingHistoryInvoiceSerializer(instance=charges, many=True)
        return serializer.data


class IsSubscribedSerializer(serializers.ModelSerializer):
    is_active = SerializerMethodField()

    class Meta:
        model = models.Subscription
        fields = ("is_active",)

    def get_is_active(self, obj):
        sub = self.context["request"].user.organization.subscription.first()
        stripe = Stripe()
        subscription = stripe.retrieve_subscription(sub_id=sub.external_id)
        return subscription.status != "canceled"

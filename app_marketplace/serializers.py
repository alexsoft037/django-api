import json
from datetime import datetime, timedelta
from logging import getLogger

from django.core.cache import cache
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.fields import JSONField
from rest_framework.status import HTTP_200_OK

from accounts.models import Membership
from cozmo_common.fields import ChoicesField
from crm.models import Contact
from listings.choices import FeeTypes, ReservationStatuses, SecurityDepositTypes, TaxTypes
from listings.models import Reservation, ReservationFee, ReservationRate
from listings.services import IsPropertyAvailable
from payments.serializers import DisputeSerializer
from rental_integrations.airbnb.choices import CancellationPolicy, MessageRole, ReservationStatus
from rental_integrations.airbnb.mappings import (
    airbnb_reservation_status,
    airbnb_reservation_status_str_to_val,
    approval_status_to_cozmo_value,
)
from rental_integrations.airbnb.models import AirbnbSync, Reservation as AirbnbReservation
from rental_integrations.airbnb.serializers import AirbnbMessageSerializer, AirbnbThreadSerializer
from send_mail.choices import DeliveryStatus, MessageType
from send_mail.models import Conversation, Message
from . import choices, models
from .exceptions import StripeError
from .services import Stripe

logger = getLogger(__name__)
webhook_logger = getLogger("webhook")


class AppSerializer(serializers.ModelSerializer):

    installed = serializers.SerializerMethodField()
    apps = serializers.SerializerMethodField()
    tags = serializers.SlugRelatedField(many=True, read_only=True, slug_field="name")

    class Meta:
        model = models.App
        fields = ("id", "name", "image", "description", "tags", "install_url", "installed", "apps")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def backend_qs(self, obj):
        try:
            backend_model = obj.backend_model
            organization_id = self.context["request"].user.organization.id
        except KeyError:
            backend_qs = models.App.objects.none()
        else:
            backend_qs = backend_model.objects.filter(organization_id=organization_id)
        return backend_qs

    def get_installed(self, obj):
        return self.backend_qs(obj).exists()

    def get_apps(self, obj):
        return self.backend_qs(obj).values_list("id", flat=True)


class VerifyCodeSerializer(serializers.Serializer):
    """Use code from OAuth2 service to retrieve user details."""

    code = serializers.CharField()
    state = serializers.CharField()
    redirect_uri = serializers.URLField()

    def __init__(self, *args, service, **kwargs):
        self.service = service
        super().__init__(*args, **kwargs)

    def validate_state(self, state):
        key = self.service.CACHE_KEY.format(state)
        user_id = cache.get(key, None)
        self._organization_id = (
            Membership.objects.filter(user_id=user_id, is_default=True)
            .values_list("organization_id", flat=True)
            .first()
        )
        if self._organization_id is None:
            raise serializers.ValidationError("Invalid state")
        return state

    def create(self, validated_data):
        return self.service.verify_access(
            {"code": validated_data["code"], "redirect_uri": validated_data["redirect_uri"]}
        )


class InstallUrlSerializer(serializers.Serializer):
    url = serializers.URLField()


class GoogleAccessSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.GoogleApp
        fields = ("user_id", "credentials")

    def create(self, validated_data):
        """Create *or* update existing instance."""
        ModelClass = self.Meta.model
        instance, _ = ModelClass.objects.update_or_create(
            organization_id=validated_data["organization_id"], defaults=validated_data
        )
        return instance


class SlackWebhookSerializer(serializers.Serializer):

    url = serializers.URLField()
    channel = serializers.CharField()
    configuration_url = serializers.URLField()


class SlackAccessSerializer(serializers.ModelSerializer):

    incoming_webhook = SlackWebhookSerializer()

    class Meta:
        model = models.SlackApp
        fields = ("access_token", "team_name", "team_id", "incoming_webhook")

    def validate(self, data):
        data.update(data.pop("incoming_webhook", {}))
        return data


class StripeAccessSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.StripeApp
        exclude = ("organization",)


class StripeUpdateSerializer(serializers.Serializer):

    signature = serializers.CharField()

    def validate(self, data):
        stripe = Stripe()
        payload = self.context["payload"]
        try:
            event = stripe.verify_event(payload, data["signature"])
        except StripeError:
            raise serializers.ValidationError("Invalid event")
        data["event"] = self._dispatch_event(event)
        return data

    def _dispatch_event(self, event):
        if event.type.startswith("charge.dispute."):
            EventSerializer = DisputeSerializer
        else:
            raise NotImplementedError(f'Event type "{event.type}" support is not implemented')
        serializer = EventSerializer(data=event.data.object)
        serializer.is_valid(raise_exception=True)
        return serializer

    def create(self, validated_data):
        validated_data["event"].save()
        return {}


class MailChimpAccessSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.MailChimpApp
        exclude = ("organization",)


class AirbnbAccessSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.AirbnbAccount
        exclude = ("organization",)


class AirbnbAvailabilitySerializer(serializers.Serializer):
    """
    Handles incoming webhook request to fetch availability
    """

    _success = {"available": True}
    _failure = {"available": False, "failure_code": None}
    test_id = "0"

    action = serializers.CharField()
    start_date = serializers.DateField()
    nights = serializers.IntegerField(min_value=1)
    listing_id = serializers.CharField()

    def validate_action(self, action):
        if action != "check_availability":
            raise serializers.ValidationError()

    def validate_listing_id(self, listing_id):
        listing_id = str(listing_id)
        if listing_id == self.test_id:
            return listing_id

        if not AirbnbSync.objects.filter(external_id=listing_id).exists():
            raise serializers.ValidationError(f"Listing {listing_id} does not exist")
        return listing_id

    def create(self, validated_data):
        if validated_data["listing_id"] == self.test_id:
            return self._success

        start_date = validated_data["start_date"]
        service = IsPropertyAvailable(
            AirbnbSync.objects.get(external_id=validated_data["listing_id"]).prop,
            start_date,
            start_date + timedelta(days=validated_data["nights"]),
        )
        service.run_check()
        response = self._success if service.is_available() else self._failure
        webhook_logger.info(
            "[webhook] - (Reservation) Response - (%s) %s", HTTP_200_OK, str(response)
        )
        return response


class GuestDetailsSerializer(serializers.Serializer):
    localized_description = serializers.CharField(required=False)
    number_of_adults = serializers.IntegerField()
    number_of_children = serializers.IntegerField()
    number_of_infants = serializers.IntegerField()


class AirbnbReservationCallSerializer(serializers.Serializer):
    """
    Handles Airbnb's initial reservation webhook to create an initial reservation or to
    check if an alteration is possible

    "This check is called before any reservation is confirmed, i.e. when the guest has
    confirmed the reservation; their payment has been charged and the availability
    has been confirmed."
    """

    _success = {"succeed": True}
    _failure = {"succeed": False, "failure_code": None}
    test_id = "0"

    confirmation_code = serializers.CharField(required=False)
    guest_id = serializers.CharField(allow_null=True, required=False)

    start_date = serializers.DateField()
    nights = serializers.IntegerField(min_value=1)
    listing_id = serializers.CharField()
    number_of_guests = serializers.IntegerField(min_value=1)
    listing_base_price = serializers.IntegerField()
    guest_details = GuestDetailsSerializer(required=False)

    @classmethod
    def with_instance(cls, confirmation_code, data):
        if str(data.get("listing_id")) == cls.test_id:
            instance = Reservation(pk=cls.test_id)
        else:
            instance = get_object_or_404(Reservation, confirmation_code=confirmation_code)
        return cls(instance=instance, data=data)

    def validate_listing_id(self, listing_id):
        listing_id = str(listing_id)
        if listing_id == self.test_id:
            return listing_id

        if not AirbnbSync.objects.filter(external_id=listing_id).exists():
            raise serializers.ValidationError(f"Listing {listing_id} does not exist")
        return listing_id

    def validate(self, data):
        if data["listing_id"] == self.test_id:
            return data

        data["prop"] = AirbnbSync.objects.get(external_id=data["listing_id"]).prop
        data["end_date"] = data["start_date"] + timedelta(days=data["nights"])
        service = IsPropertyAvailable(
            data["prop"],
            data["start_date"],
            data["end_date"],
            reservations_excluded=[] if self.instance is None else [self.instance],
        )
        data["is_available"] = False
        service.run_check()
        if service.is_available():
            data["is_available"] = True
        return data

    def create(self, validated_data):
        if validated_data["listing_id"] == self.test_id:
            return self._success

        if not validated_data["is_available"]:
            return self._failure

        guest_details = validated_data.get("guest_details", None)
        if validated_data["listing_id"] != self.test_id:
            reservation_data = dict(
                start_date=validated_data["start_date"],
                end_date=validated_data["end_date"],
                base_total=validated_data["listing_base_price"],
                price=validated_data["listing_base_price"],
                guests_adults=validated_data["number_of_guests"],
                confirmation_code=validated_data["confirmation_code"],
                status=ReservationStatuses.Inquiry.value,
                prop=validated_data["prop"],
                source=Reservation.Sources.Airbnb,
            )
            if guest_details:
                new_reservation_data = dict(
                    guests_adults=guest_details["number_of_adults"],
                    guests_children=guest_details["number_of_children"],
                    guests_infants=guest_details["number_of_infants"],
                )
                reservation_data.update(new_reservation_data)
            reservation, _ = Reservation.objects.update_or_create(**reservation_data)

            AirbnbReservation.objects.update_or_create(
                reservation_id=reservation.id,
                confirmation_code=validated_data["confirmation_code"],
                listing_base_price=validated_data["listing_base_price"],
                guest_id=validated_data["guest_id"],
                is_preconfirmed=True,
            )
            Conversation.objects.update_or_create(reservation=reservation)
        return self._success

    def update(self, instance, validated_data):
        if instance.pk == self.test_id:
            return self._success

        if not validated_data["is_available"]:
            return self._failure

        return self._success


class AirbnbReservationSerializer(AirbnbAvailabilitySerializer):
    _success = {"succeed": True}
    _failure = {"succeed": False, "failure_code": None}

    confirmation_code = serializers.CharField(required=False)
    number_of_guests = serializers.IntegerField(min_value=1)
    guest_details = GuestDetailsSerializer(required=False)
    guest_id = serializers.CharField(allow_null=True, required=False)
    guest_email = serializers.EmailField(allow_null=True, required=False)
    guest_first_name = serializers.CharField(allow_null=True, required=False)
    guest_last_name = serializers.CharField(allow_null=True, required=False)
    guest_phone_numbers = serializers.ListField(child=serializers.CharField(), required=False)
    guest_preferred_locale = serializers.CharField(allow_null=True, required=False)
    # following fields are used in notifications
    thread_id = serializers.IntegerField(required=False)
    status_type = serializers.ChoiceField(choices=ReservationStatus.choices(), required=False)
    cancellation_policy_category = serializers.ChoiceField(
        choices=CancellationPolicy.choices(), required=False
    )
    booked_at = serializers.DateTimeField(allow_null=True, required=False)
    created_at = serializers.DateTimeField(allow_null=True, required=False)
    updated_at = serializers.DateTimeField(allow_null=True, required=False)

    # Airbnb pricing data
    expected_payout_amount_accurate = serializers.CharField(allow_null=True, required=False)
    listing_base_price = serializers.IntegerField(allow_null=True, required=False)
    listing_base_price_accurate = serializers.CharField(allow_null=True, required=False)
    listing_host_fee_accurate = serializers.CharField(allow_null=True, required=False)
    listing_cancellation_host_fee_accurate = serializers.CharField(allow_null=True, required=False)
    listing_cancellation_payout_accurate = serializers.CharField(allow_null=True, required=False)
    listing_security_price_accurate = serializers.CharField(allow_null=True, required=False)
    listing_cleaning_fee_accurate = serializers.CharField(allow_null=True, required=False)
    occupancy_tax_amount_paid_to_host_accurate = serializers.CharField(
        allow_null=True, required=False
    )
    transient_occupancy_tax_paid_amount_accurate = serializers.CharField(
        allow_null=True, required=False
    )
    total_paid_amount_accurate = serializers.CharField(allow_null=True, required=False)
    standard_fees_details = serializers.ListField(
        child=JSONField(), allow_empty=True, required=False
    )
    transient_occupancy_tax_details = serializers.ListField(
        child=JSONField(), allow_empty=True, required=False
    )

    action = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance is None:
            self.fields["guest_id"].required = False
            self.fields["confirmation_code"].required = False

    @classmethod
    def with_instance(cls, confirmation_code, data):
        if str(data.get("listing_id")) == cls.test_id:
            instance = Reservation(pk=cls.test_id)
        else:
            instance = get_object_or_404(Reservation, confirmation_code=confirmation_code)
        return cls(instance=instance, data=data)

    def validate_confirmation_code(self, confirmation_code):
        if self.instance is not None and confirmation_code is None:
            self.fail("required")
        return confirmation_code

    def validate_guest_id(self, guest_id):
        if self.instance is not None and guest_id is None:
            self.fail("required")
        return guest_id

    def validate(self, data):
        if data["listing_id"] == self.test_id:
            return data

        data["prop"] = AirbnbSync.objects.get(external_id=data["listing_id"]).prop
        data["end_date"] = data["start_date"] + timedelta(days=data["nights"])
        service = IsPropertyAvailable(
            data["prop"],
            data["start_date"],
            data["end_date"],
            reservations_excluded=[] if self.instance is None else [self.instance],
        )
        service.run_check()
        return data

    def create(self, validated_data):
        if validated_data["listing_id"] != self.test_id:
            guest_data = {
                "last_name": validated_data["guest_last_name"],
                "first_name": validated_data["guest_first_name"],
                "email": validated_data["guest_email"],
                "phone": validated_data["guest_phone_numbers"][0],
                "external_id": validated_data["guest_id"],
                "organization": validated_data["prop"].organization,
            }

            guest, _ = Contact.objects.update_or_create(
                email=guest_data["email"],
                organization=guest_data["organization"],
                defaults=guest_data,
            )

            guest_details = validated_data.get("guest_details", None)
            reservation_data = dict(
                start_date=validated_data["start_date"],
                end_date=validated_data["end_date"],
                price=validated_data["listing_base_price"],
                paid=validated_data["total_paid_amount_accurate"],
                guests_adults=validated_data["number_of_guests"],
                confirmation_code=validated_data["confirmation_code"],
                status=airbnb_reservation_status[validated_data["status_type"]],
                guest=guest,
                prop=validated_data["prop"],
                source=Reservation.Sources.Airbnb,
            )
            if guest_details:
                new_reservation_data = dict(
                    guests_adults=guest_details["number_of_adults"],
                    guests_children=guest_details["number_of_children"],
                    guests_infants=guest_details["number_of_infants"],
                )
                reservation_data.update(new_reservation_data)

            reservation, _ = Reservation.objects.update_or_create(
                confirmation_code=validated_data["confirmation_code"], defaults=reservation_data
            )

            AirbnbReservation.objects.update_or_create(
                reservation=reservation,
                defaults=dict(
                    listing_host_fee_accurate=validated_data["listing_host_fee_accurate"],
                    guest_id=validated_data["guest_id"],
                    guest_last_name=validated_data["guest_last_name"],
                    guest_first_name=validated_data["guest_first_name"],
                    guest_email=validated_data["guest_email"],
                    guest_preferred_locale=validated_data["guest_preferred_locale"],
                    confirmation_code=validated_data["confirmation_code"],
                    listing_base_price=validated_data["listing_base_price"],
                    is_preconfirmed=False,
                    booked_at=validated_data["booked_at"],
                    updated_at=validated_data["updated_at"],
                    created_at=validated_data["created_at"],
                    status_type=validated_data["status_type"],
                    cancellation_policy_category=validated_data["cancellation_policy_category"],
                ),
            )

            Conversation.objects.update_or_create(
                reservation_id=reservation.id, defaults=dict(thread_id=validated_data["thread_id"])
            )
        return self._success

    def update(self, instance, validated_data):
        if instance.pk == self.test_id:
            return self._success

        guest_data = {
            "last_name": validated_data["guest_last_name"],
            "first_name": validated_data["guest_first_name"],
            "email": validated_data["guest_email"],
            "phone": validated_data["guest_phone_numbers"][0],
            "external_id": validated_data["guest_id"],
            "organization": validated_data["prop"].organization,
        }
        guest, _ = Contact.objects.update_or_create(
            email=guest_data["email"], organization=guest_data["organization"], defaults=guest_data
        )
        status_type = validated_data["status_type"]
        start_date = validated_data["start_date"]

        self.instance.start_date = start_date
        self.instance.end_date = start_date + timedelta(days=validated_data["nights"])
        self.instance.guests_adults = validated_data["number_of_guests"]
        self.instance.guest = guest
        self.instance.status = airbnb_reservation_status_str_to_val.get(status_type)
        self.instance.price = float(validated_data["expected_payout_amount_accurate"])
        self.instance.paid = float(validated_data["expected_payout_amount_accurate"])

        guest_details = validated_data.get("guest_details", None)
        if guest_details:
            self.instance.guests_adults = guest_details["number_of_adults"]
            self.instance.guests_children = guest_details["number_of_children"]
            self.instance.guests_infants = guest_details["number_of_infants"]

        self.instance.save()

        expected_payout_amount = validated_data["expected_payout_amount_accurate"]
        listing_base_price = validated_data["listing_base_price_accurate"]
        listing_host_fee = validated_data["listing_host_fee_accurate"]
        listing_cancellation_host_fee = validated_data["listing_cancellation_host_fee_accurate"]
        listing_cancellation_payout = validated_data["listing_cancellation_payout_accurate"]
        listing_security_price = validated_data["listing_security_price_accurate"]
        listing_cleaning_fee = validated_data["listing_cleaning_fee_accurate"]
        occupancy_tax_paid_to_host = validated_data["occupancy_tax_amount_paid_to_host_accurate"]
        transient_tax_paid_amount = validated_data["transient_occupancy_tax_paid_amount_accurate"]
        total_paid_amount = validated_data["total_paid_amount_accurate"]
        standard_fees_details = validated_data["standard_fees_details"]
        transient_tax_details = validated_data["transient_occupancy_tax_details"]

        #  Host cancelled means there is no payout
        if self.instance.status == ReservationStatuses.Cancelled.value:
            ReservationRate.objects.update_or_create(
                reservation=self.instance,
                defaults=dict(
                    duration=validated_data["nights"], value=listing_cancellation_payout
                ),
            )
        else:
            ReservationRate.objects.update_or_create(
                reservation=self.instance,
                defaults=dict(duration=validated_data["nights"], value=listing_base_price),
            )

        ReservationFee.objects.update_or_create(
            reservation=self.instance,
            name="Airbnb Host Fee",
            defaults=dict(
                value=float(listing_host_fee) * -1, fee_tax_type=FeeTypes.Platform_Fee, custom=True
            ),
        )
        if listing_cleaning_fee:
            ReservationFee.objects.update_or_create(
                reservation=self.instance,
                name="Cleaning Fee",
                defaults=dict(
                    value=float(listing_cleaning_fee),
                    fee_tax_type=FeeTypes.Service_Fee,
                    custom=True,
                ),
            )
        if listing_security_price:
            ReservationFee.objects.update_or_create(
                reservation=self.instance,
                name="Security Deposit",
                defaults=dict(
                    value=float(listing_security_price),
                    fee_tax_type=SecurityDepositTypes.Security_Deposit,
                    refundable=True,
                    custom=True,
                ),
            )
        if transient_tax_details:
            for tax in transient_tax_details:
                ReservationFee.objects.update_or_create(
                    reservation=self.instance,
                    name=tax["name"],
                    defaults=dict(
                        value=float(tax["amount_usd"]),
                        fee_tax_type=TaxTypes.Local_Tax,
                        custom=True,
                    ),
                )
        if standard_fees_details:
            for fee in standard_fees_details:
                ReservationFee.objects.update_or_create(
                    reservation=self.instance,
                    name=fee["fee_type"],
                    defaults=dict(value=float(fee["amount_native"]), custom=True),
                )

        conversation, _ = Conversation.objects.update_or_create(
            reservation=self.instance, defaults=dict(thread_id=validated_data["thread_id"])
        )

        external, _ = AirbnbReservation.objects.update_or_create(
            reservation=self.instance,
            defaults=dict(
                is_preconfirmed=False,
                guest_id=validated_data["guest_id"],
                guest_last_name=validated_data["guest_last_name"],
                guest_first_name=validated_data["guest_first_name"],
                guest_email=validated_data["guest_email"],
                guest_phone_numbers=json.dumps(validated_data["guest_phone_numbers"]),
                guest_preferred_locale=validated_data["guest_preferred_locale"],
                confirmation_code=validated_data["confirmation_code"],
                booked_at=validated_data["booked_at"],
                updated_at=validated_data["updated_at"],
                created_at=validated_data["created_at"],
                status_type=validated_data["status_type"],
                cancellation_policy_category=validated_data["cancellation_policy_category"],
                expected_payout_amount_accurate=expected_payout_amount,
                listing_host_fee_accurate=listing_host_fee,
                listing_base_price_accurate=listing_base_price,
                listing_cleaning_fee_accurate=listing_cleaning_fee,
                listing_cancellation_host_fee_accurate=listing_cancellation_host_fee,
                listing_cancellation_payout_accurate=listing_cancellation_payout,
                listing_security_price_accurate=listing_security_price,
                occupancy_tax_amount_paid_to_host_accurate=occupancy_tax_paid_to_host,
                transient_occupancy_tax_paid_amount_accurate=transient_tax_paid_amount,
                total_paid_amount_accurate=total_paid_amount,
                standard_fees_details=json.dumps(standard_fees_details),
                transient_occupancy_tax_details=json.dumps(transient_tax_details),
                thread_id=validated_data["thread_id"],
            ),
        )

        return self._success


class AirbnbNotifySerializer(serializers.Serializer):
    _success = {"succeed": True}
    _failure = {"succeed": False, "failure_code": None}

    action = serializers.CharField()

    def create(self, data):
        logger.warning("Airbnb webhook: use dedicated serializer for %s", data["action"])
        return data


class AirbnbReservationCancellationNotifySerializer(AirbnbNotifySerializer):

    reservation = AirbnbReservationSerializer()

    def validate_reservation(self, reservation):
        confirmation_code = reservation["confirmation_code"]
        serializer = AirbnbReservationSerializer.with_instance(confirmation_code, reservation)
        serializer.is_valid(raise_exception=True)
        return serializer

    def create(self, data):
        data["reservation"].save()
        return data


class AirbnbReservationNotifySerializer(AirbnbNotifySerializer):

    message_to_host = serializers.CharField(allow_null=True, required=False)
    reservation = AirbnbReservationSerializer()

    def validate_reservation(self, reservation):
        confirmation_code = reservation["confirmation_code"]
        serializer = AirbnbReservationSerializer.with_instance(confirmation_code, reservation)
        serializer.is_valid(raise_exception=True)
        return serializer

    def create(self, data):
        data["reservation"].save()
        return data


class AirbnbNotifyApprovalSerializer(AirbnbNotifySerializer):
    class ListingApprovalSerializer(serializers.Serializer):
        listing_id = serializers.IntegerField()
        approval_status_category = ChoicesField(choices=choices.AirbnbApprovalStatus)
        notes = serializers.CharField(
            required=False, min_length=0, allow_blank=True, allow_null=True
        )
        listing_import_id = serializers.IntegerField(required=False, allow_null=True)
        host_id = serializers.IntegerField(required=False, allow_null=True)

        def create(self, data):
            # TODO notes should be converted into structured requirements
            converted_status = approval_status_to_cozmo_value[data["approval_status_category"]]
            if data["approval_status_category"] == choices.AirbnbApprovalStatus.approved:
                airbnb_sync = AirbnbSync.objects.get(external_id=data["listing_id"])
                airbnb_sync.approval_status = converted_status
                airbnb_sync.save()
            return data

    listing_approval_status = ListingApprovalSerializer()

    def create(self, data):
        return self.fields["listing_approval_status"].create(
            data["listing_approval_status"]
        )  # FIXME


class AirbnbNotifySyncSerializer(AirbnbNotifySerializer):
    class UpdateSerializer(serializers.Serializer):
        listing_id = serializers.IntegerField()
        synchronization_category = ChoicesField(choices=choices.AirbnbSyncCategory)
        after_mapping_listing_id = serializers.IntegerField(required=False)

        def create(self, data):
            AirbnbSync.objects.filter(external_id=data["listing_id"]).update(
                scope=data["synchronization_category"]  # TODO convert this
            )
            if data.get("after_mapping_listing_id"):
                AirbnbSync.objects.filter(external_id=data["listing_id"]).update(
                    external_id=data["after_mapping_listing_id"]
                )
            return data

    host_id = serializers.IntegerField()
    updates = UpdateSerializer(many=True)

    def create(self, data):
        return self.fields["updates"].create(data["updates"])  # FIXME


class AirbnbNotifyUnlinkedSerializer(AirbnbNotifySerializer):
    host_id = serializers.IntegerField()
    listing_ids = serializers.ListSerializer(child=serializers.CharField(), allow_empty=True)

    def create(self, data):
        for app in (
            models.AirbnbAccount.objects.filter(user_id=data["host_id"])
            .only("id", "access_token")
            .prefetch_related("airbnbsync_set")
        ):
            app.airbnbsync_set.filter(external_id__in=data["listing_ids"]).delete()
            # TODO do i need to delete listings?
            # app.listing_set.filter(external_id__in=data["listing_ids"]).delete()

        return data


class AirbnbNotifyAuthRevokedSerializer(AirbnbNotifySerializer):
    host_id = serializers.IntegerField()
    listing_ids = serializers.ListSerializer(child=serializers.CharField(), allow_empty=True)

    def create(self, data):
        for app in (
            models.AirbnbAccount.objects.filter(user_id=data["host_id"])
            .only("id", "access_token")
            .prefetch_related("airbnbsync_set")
        ):
            app.airbnbsync_set.all().delete()
            app.delete()

        return data


class AirbnbNotifyMessageAddedSerializer(AirbnbNotifySerializer):
    """
    Airbnb message notifications are sent whenever a message has been posted to Airbnb. This
    includes sending messages from the Airbnb site or through the API integration.

    Messages are received for the following reasons
    * Host messages the guest via Cozmo
    * Host messages the guest via Airbnb (usually through cancellation messages)
    * Guest messages via Airbnb

    It also appears that Airbnb will send this notification in place of a reservation confirmation
    notification.
    """

    message = AirbnbMessageSerializer()
    thread = AirbnbThreadSerializer()
    OWNER_ROLES = [MessageRole.owner.value, MessageRole.cohost.value]
    GUEST_ROLES = [MessageRole.guest.value, MessageRole.booker.value]

    def create(self, data):
        thread = data["thread"]
        attachment = thread["attachment"]
        booking_details = attachment["booking_details"]
        message = data["message"]
        listing_id = booking_details["listing_id"]
        confirmation_code = booking_details["reservation_confirmation_code"]
        # users = thread["users"]

        try:
            # Fetch airbnb reservation if exists
            airbnb_reservation = AirbnbReservation.objects.get(confirmation_code=confirmation_code)
            # Fetch updated reservation data. This is done here because in some cases, we do
            # not receive the reservation webhooks. This is mostly a concern with the dev env
            # which we are currently using to hack. If we can't find an AirbnbSync object,
            # we just ignore...
            # with suppress(AirbnbSync.DoesNotExist):
            #     sync = AirbnbSync.objects.get(external_id=listing_id)
            #     r = sync.account.service.get_reservation_by_confirmation_code(confirmation_code)
            #     serializer = AirbnbReservationSerializer(airbnb_reservation.reservation, data=r)
            #     if not serializer.is_valid():
            #         return self._failure
            #     serializer.save()
        except AirbnbReservation.DoesNotExist:
            # If reservation is not found, then the corresponding reservation was never created.
            # So we check to see if there is a sync object and if so, we fetch the reservation,
            # and create it. If there is no sync object, we can safely say that the corresponding
            # reservation should not exist anymore and the message webhook will be ignored.
            try:
                sync = AirbnbSync.objects.get(external_id=listing_id)
                r = sync.account.service.get_reservation_by_confirmation_code(confirmation_code)
                serializer = AirbnbReservationSerializer(data=r)
                if not serializer.is_valid():
                    return self._failure
                airbnb_reservation = serializer.save()
            except AirbnbSync.DoesNotExist:
                return self._failure

        reservation = airbnb_reservation.reservation
        sender_user_id = message["user_id"]
        roles = attachment["roles"]
        outgoing = False
        # is_host = False
        for r in roles:
            if sender_user_id in r["user_ids"] and r["role"] in self.OWNER_ROLES:
                outgoing = True
                break
        # user = None
        # for u in users:
        #     if sender_user_id == u["id"]:
        #         user = u
        #         break
        # status = attachment["status"]
        # if status == MessageReservationStatus.accepted.value:
        #     pass

        # if not is_host:
        #     guest_data = {
        #         "last_name": user["first_name"],
        #         "external_id": user["id"],
        #         "organization": reservation.prop.organization,
        #     }
        #     guest, _ = Contact.objects.update_or_create(
        #         email=guest_data["email"],
        #         organization=guest_data["organization"],
        #         defaults=guest_data
        #     )

        airbnb_reservation.expected_payout_amount_accurate = booking_details[
            "expected_payout_amount_accurate"
        ]
        airbnb_reservation.thread_id = thread["id"]
        airbnb_reservation.save()

        conversation = reservation.conversation
        conversation.thread_id = thread["id"]
        conversation.save()

        reservation.guests_adults = booking_details["number_of_adults"]
        reservation.guests_children = booking_details["number_of_children"]
        reservation.guests_infants = booking_details["number_of_infants"]
        # reservation.status = airbnb_reservation_status_str_to_val.get(status)
        reservation.save()

        recipient_info = {
            "thread_id": thread["id"]
        }
        # Use Message instead of APIMessage to not trigger signals
        message, created = Message.objects.update_or_create(
            external_id=str(message["id"]),
            defaults=dict(
                type=MessageType.api.value,
                recipient=reservation.conversation.thread_id,
                text=message["message"],
                sender=getattr(reservation.prop.owner, "email", ""),
                recipient_info=recipient_info,
                outgoing=outgoing,
                conversation=conversation,
                external_id=message["id"],
                external_date_created=message["created_at"],
                date_delivered=datetime.now(),
                delivery_status=DeliveryStatus.delivered,
            ),
        )
        logger.debug(f"processed APIMessage: {message}, {created}")
        return self._success

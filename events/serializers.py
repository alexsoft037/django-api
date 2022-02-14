from contextlib import suppress

from django.contrib.auth import get_user_model
from rest_framework.fields import SerializerMethodField
from rest_framework.serializers import ModelSerializer

from cozmo_common.fields import ChoicesField
from .choices import EventType
from .models import Event

User = get_user_model()


class ReservationEventSerializer(ModelSerializer):

    name = SerializerMethodField()
    guest_name = SerializerMethodField()
    category = SerializerMethodField()
    serializer_choice_field = ChoicesField

    class Meta:
        model = Event
        fields = ("event_type", "category", "timestamp", "context", "name", "guest_name")

    def get_name(self, obj):
        user_id = obj.context.get("request_user_id")
        user_name = ""

        with suppress(User.DoesNotExist):
            user = User.objects.get(pk=user_id)
            user_name = user.first_name if user.first_name else user.username

        guest_name = self.get_guest_name(obj)

        return {
            EventType.Inquiry.value: f"{user_name} created inquiry",
            EventType.Agreement_signed.value: f"{guest_name} signed agreement",
            EventType.Agreement_rejected.value: f"{guest_name} rejected agreement",
            EventType.Agreement_sent.value: f"{user_name} sent agreement",
            EventType.Quote_sent.value: f"{user_name} sent quote",
            EventType.Reservation_created.value: f"{user_name} created reservation",
            EventType.Reservation_modified.value: f"{user_name} modified reservation",
            EventType.Reservation_cancelled.value: f"{user_name} cancelled reservation",
            EventType.Reservation_cancellation_request.value: "Reservation cancellation request",
            EventType.Notes_changed.value: "Notes changed",
            EventType.Message_received.value: "Message received",
            EventType.Message_sent.value: "Message sent",
            EventType.Welcome_letter_sent.value: "Welcome letter sent",
            EventType.Reminder_sent.value: "Reminder sent",
            EventType.Payment.value: "Payment",
            EventType.Refund.value: "Refund",
            EventType.Dispute.value: "Dispute",
        }.get(obj.event_type)

    def get_guest_name(self, obj):
        guest = obj.content_object.guest
        if guest:
            guest_name = guest.first_name if guest.first_name else guest.email
        else:
            guest_name = "Guest"
        return guest_name

    def get_category(self, obj):
        return obj.content_object._meta.model_name

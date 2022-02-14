from rest_framework import serializers
from rest_framework.fields import SerializerMethodField
from rest_framework.serializers import ModelSerializer

from listings.models import Reservation
from listings.serializers import ReservationSerializer
from send_mail.models import Message


class BookingSerializer(ReservationSerializer):

    class Meta:
        model = Reservation
        fields = (
            "id",
            "start_date",
            "end_date",
            "price",
            "guest",
            "external_id",
            "status",
            "source",
            "base_total",
            "price_total",
            "currency",
            "prop"
        )


class BookingsDashboardSerializer(serializers.Serializer):
    arrivals = BookingSerializer(many=True)
    departures = BookingSerializer(many=True)


class TodoDashboardSerializer(serializers.Serializer):
    title = serializers.CharField(min_length=10)
    url = serializers.CharField(min_length=10)
    text = serializers.CharField(min_length=10)
    icon = serializers.CharField(min_length=10)


class InboxDashbordSerializer(ModelSerializer):
    reservation_id = SerializerMethodField()
    recipient = SerializerMethodField()

    class Meta:
        model = Message
        fields = (
            "id",
            "recipient",
            "recipient_info",
            "type",
            "text",
            "sender",
            "reservation_id",
            "date_created"
        )

    def get_recipient(self, obj):
        return obj.conversation.reservation.guest.full_name

    def get_reservation_id(self, obj):
        return obj.conversation.reservation_id


class DashboardSerializer(serializers.Serializer):
    bookings = BookingsDashboardSerializer(read_only=True)
    todo = TodoDashboardSerializer(many=True, read_only=True)
    messages = InboxDashbordSerializer(many=True, read_only=True)

from rest_framework import serializers
from rest_framework.fields import SerializerMethodField
from twilio.twiml.messaging_response import MessagingResponse

from listings.models import Reservation
from send_mail.models import Message
from send_mail.serializers import MessageSerializer
from vendors.serializers import JobSerializer
from . import models


class ReservationPayloadNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reservation
        fields = (
            "id",
            "prop",
            "guest",
            "start_date",
            "end_date",
            "status",
            "confirmation_code",
            "source",
            "date_updated",
            "date_created",
        )


class ContentObjectRelatedField(serializers.RelatedField):

    def to_representation(self, value):
        if isinstance(value, Reservation):
            return ReservationPayloadNotificationSerializer(instance=value).data
        elif isinstance(value, Message):
            return MessageSerializer(instance=value).data
        elif isinstance(value, Message):
            return JobSerializer(instance=value).data
        raise Exception("Unexpected type of tagged object")


class NotificationSerializer(serializers.ModelSerializer):

    url = SerializerMethodField()
    payload = ContentObjectRelatedField(source="content_object", read_only=True)

    def get_url(self, obj):
        url = ""
        if isinstance(obj.content_object, Reservation):
            url = f"/reservations/{obj.object_id}/"
        elif isinstance(obj.content_object, Message):
            url = f"/reservations/{obj.content_object.conversation.reservation.id}"
        return url

    class Meta:
        model = models.Notification
        fields = (
            "id",
            "is_sent",
            "content",
            "date_created",
            "is_read",
            "payload",
            "url",
        )


class TwilioReplySerializer(serializers.ModelSerializer):
    """Serializer that accepts and responds to Twilio Webhook.

    NOTE: It will not create any `TwilioReply` instances, it is read/update only.
    """

    MessageSid = serializers.CharField(source="message_id", max_length=34)
    Body = serializers.CharField(max_length=1600, required=True, write_only=True)

    class Meta:
        model = models.TwilioReply
        fields = ("MessageSid", "Body")

    def validate_MessageSid(self, message_id):
        if not self.instance:
            raise serializers.ValidationError("No such message")
        return message_id

    def validate_Body(self, body):
        body = body.upper()
        if self.instance and body not in self.instance.content_object.REPLY_MAP:
            raise serializers.ValidationError("Invalid response")
        return body

    def save(self, **kwargs):
        """Update status of related `content_object`."""
        content_obj = self.instance.content_object

        content_obj.status = content_obj.REPLY_MAP[self.validated_data["Body"]]
        content_obj.save()

        return self.instance

    @property
    def response(self):
        """Response to an user based on incoming data."""
        return str(MessagingResponse())

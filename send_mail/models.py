import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import JSONField
from django.db import models

from accounts.models import Organization
from cozmo.storages import UploadImageTo
from cozmo_common.db.models import TimestampModel
from listings.models import Reservation
from send_mail.choices import DeliveryStatus, MessageType, Status
from send_mail.managers import (
    APIMessageManager,
    EmailMessageManager,
    MessageManager,
    SMSMessageManager,
)
from send_mail.querysets import ConversationQuerySet

User = get_user_model()


class Conversation(TimestampModel):
    reservation = models.OneToOneField(Reservation, on_delete=models.CASCADE)
    thread_id = models.CharField(default="", blank=True, max_length=250)
    unread = models.BooleanField(default=False)

    objects = ConversationQuerySet.as_manager()

    class Meta:
        ordering = ("date_updated",)
        permissions = (("view_conversation", "Can view conversation"),)


class Message(TimestampModel):
    """
    Base message model for all types of messages
     - SMS
     - Email (Managed) - Cozmo send via Sendgrid, etc
     - Email (Unmanaged) - Gmail, etc
     - External messaging API
    """

    recipient_info = JSONField(default={})
    recipient = models.CharField(max_length=128)
    text = models.TextField(default="")  # Change to body
    html_text = models.TextField(default="")
    sender = models.CharField(max_length=128)
    outgoing = models.BooleanField(default=True, blank=True)
    type = models.PositiveSmallIntegerField(choices=MessageType.choices(), null=True)
    conversation = models.ForeignKey(
        Conversation, related_name="messages", on_delete=models.CASCADE, null=True
    )
    # External messaging API
    external_id = models.CharField(max_length=128, null=True, default=None)
    external_date_created = models.DateTimeField(null=True, blank=True, default=None)
    external_date_updated = models.DateTimeField(null=True, blank=True, default=None)
    # Email only fields
    subject = models.TextField(default="", blank=True)

    delivery_status = models.PositiveSmallIntegerField(
        choices=DeliveryStatus.choices(), default=DeliveryStatus.not_started
    )
    date_delivered = models.DateTimeField(null=True, default=None)

    automated = models.BooleanField(default=False)
    # For automated email parsing purposes
    external_email_id = models.CharField(max_length=512, blank=True, default="")
    reply_to_reference = models.CharField(max_length=512, blank=True, default="")

    # Where the message was sourced (i.e. email, api, etc)
    # source = models.PositiveSmallIntegerField()

    objects = MessageManager()

    class Meta:
        indexes = [models.Index(fields=["conversation", "date_created"])]
        permissions = (("view_message", "Can view messages"),)


class APIMessage(Message):
    objects = APIMessageManager()

    class Meta:
        proxy = True


class EmailMessage(Message):
    objects = EmailMessageManager()

    class Meta:
        proxy = True


class SMSMessage(Message):
    objects = SMSMessageManager()

    class Meta:
        proxy = True


class Attachment(models.Model):

    name = models.CharField(max_length=250)
    url = models.FileField(upload_to=UploadImageTo("mail/attachments"))
    message = models.ForeignKey(Message, on_delete=models.CASCADE)


def generate_name():
    return uuid.uuid4().hex[:12].upper()


class ForwardingEmail(models.Model):

    name = models.CharField(default=generate_name, unique=True, max_length=255)
    enabled = models.BooleanField(default=True)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="forwarding_emails"
    )

    class Meta:
        permissions = (("view_forwardingemail", "Can view forwarding emails"),)

    @property
    def address(self):
        return f"{self.name}@{settings.PARSE_EMAIL_DOMAIN}"


class Task(TimestampModel):

    status = models.PositiveSmallIntegerField(choices=Status.choices(), default=Status.init)
    error = models.TextField(blank=True, default="")
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True)
    object_id = models.PositiveIntegerField(null=True)
    content_object = GenericForeignKey("content_type", "object_id")

    class Meta:
        abstract = True


class ParseEmailTask(Task):
    data = JSONField(default={})


class ParseEmailAttachment(models.Model):
    name = models.CharField(max_length=250)
    url = models.FileField(upload_to=UploadImageTo("parse/emails/attachments"))
    task = models.ForeignKey(ParseEmailTask, on_delete=models.CASCADE, related_name="attachments")

import logging

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import JSONField
from django.db import models

from cozmo_common.enums import ChoicesEnum
from cozmo_common.functions import send_html_content_email
from notifications.services.sms import ServiceError, TwilioService

logger = logging.getLogger(__name__)


class Notification(models.Model):
    class Channels(ChoicesEnum):
        SMS = 1
        Email = 2
        Slack = 3

    channel = models.PositiveSmallIntegerField(choices=Channels.choices())
    is_sent = models.BooleanField(default=False)
    content = models.TextField(blank=True)
    date_created = models.DateTimeField(auto_now_add=True, editable=False)
    to = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    content_data = JSONField(null=True, default=None)
    is_read = models.BooleanField(default=False)

    def send(self, commit=True):
        if self.channel == self.Channels.SMS.value:
            self._send_sms()
        elif self.channel == self.Channels.Email.value:
            self._send_email()
        else:
            logger.debug(
                "Notification by %s is currently unsupported", self.Channels(self.channel)
            )
        self.is_sent = True
        if commit:
            self.save()

    def _send_email(self):
        try:
            send_html_content_email(self.content, "Voyajoy - Email Confirmation", self.to.email)
        except Exception as e:
            logger.info("Could not send email: %s", e.args)
        else:
            logger.info("Notification id=%s sent", self.id)

    def _send_sms(self):
        service = TwilioService()
        try:
            message_id = service.send(text=self.content, to=self.to.phone)
        except ServiceError as e:
            logger.info("Notification could not be sent: %s", (e.__cause__ or e))
        else:
            logger.info("Notification id=%s sent", self.id)
            TwilioReply.objects.create(message_id=message_id, content_object=self.content_object)


class TwilioReply(models.Model):

    message_id = models.CharField(max_length=34, primary_key=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")


import logging

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from automation.models import ReservationMessage
from automation.utils import html_to_text
from message_templates.choices import TransportMethod
from send_mail.models import APIMessage, EmailMessage, SMSMessage

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ReservationMessage)
def send_reservation_message(sender, **kwargs):
    created = kwargs["created"]
    if created:
        instance = kwargs["instance"]
        message_method_object_mapping = {
            TransportMethod.EMAIL: EmailMessage,
            TransportMethod.MESSAGE: APIMessage,
            TransportMethod.SMS: SMSMessage,
        }
        method = instance.schedule.method
        message_object = message_method_object_mapping.get(method)
        logger.info("sending via: {}".format(message_object))
        reservation = instance.reservation
        message_data = dict(
            subject=instance.subject,
            text=html_to_text(instance.content),
            html_text=instance.content,
            conversation=reservation.conversation,
            outgoing=True,
            sender=settings.DEFAULT_EMAIL_SENDER,
            recipient=instance.recipient,
            recipient_info=instance.recipient_info,
            automated=True
        )

        logger.info(message_data)

        if method == TransportMethod.AUTO:
            message_object = (
                APIMessage if hasattr(reservation, "external_reservation") else EmailMessage
            )
        instance.message = message_object.objects.create(**message_data)
        instance.save()

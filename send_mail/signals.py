import logging
from datetime import datetime

from django.db.models.signals import post_save
from django.dispatch import receiver

from chat.services import ChatService
from notifications.services.sms import ServiceError
from send_mail.choices import DeliveryStatus
from send_mail.phone.models import Number
from send_mail.services import send_airbnb_message, send_email, send_sms
from .models import APIMessage, EmailMessage, Message, SMSMessage

logger = logging.getLogger(__name__)


@receiver(post_save, sender=SMSMessage)
def send_sms_message(sender, **kwargs):
    created = kwargs["created"]
    if created:
        instance = kwargs["instance"]
        if instance.delivery_status != DeliveryStatus.not_started:
            return
        organization = instance.conversation.reservation.prop.organization
        phone = Number.objects.get(organization=organization)
        instance.delivery_status = DeliveryStatus.started
        instance.save()
        try:
            send_sms(_from=phone.msisdn, to=instance.recipient.phone, text=instance.text)
            instance.date_delivered = datetime.now()
            instance.delivery_status = DeliveryStatus.delivered
        except Exception as e:
            instance.date_delivered = datetime.now()
            instance.delivery_status = DeliveryStatus.failed
        finally:
            instance.save()


@receiver(post_save, sender=EmailMessage)
def send_email_message(sender, **kwargs):
    created = kwargs["created"]
    if created:
        instance = kwargs["instance"]
        if instance.delivery_status != DeliveryStatus.not_started:
            return
        text = instance.html_text
        instance.delivery_status = DeliveryStatus.started
        instance.save()
        try:
            send_email(
                _from=instance.sender,
                to=instance.recipient,
                text=text,
                subject=instance.subject,
                attachments=list(),
                cc=instance.recipient_info.get("cc"),
                bcc=instance.recipient_info.get("bcc"),
                headers={"In-Reply-To": instance.reply_to_reference}
                if instance.reply_to_reference
                else None,
            )
            instance.delivery_status = DeliveryStatus.delivered
            instance.date_delivered = datetime.now()
        except ServiceError as e:
            logger.debug("Failed to send email id={}".format(instance.id))
            instance.delivery_status = DeliveryStatus.failed
        finally:
            instance.save()


@receiver(post_save, sender=APIMessage)
def send_api_message(sender, **kwargs):
    created = kwargs["created"]
    if created:
        instance = kwargs["instance"]
        if instance.delivery_status != DeliveryStatus.not_started:
            return
        instance.delivery_status = DeliveryStatus.started
        instance.save()
        message = None
        try:
            message = send_airbnb_message(
                organization=instance.conversation.reservation.prop.organization,
                external_id=instance.conversation.thread_id,
                text=instance.text,
                attachments=list(),
            )
            instance.external_date_created = message["created_at"]
            instance.external_id = message["id"]
            instance.date_delivered = datetime.now()
            instance.delivery_status = DeliveryStatus.delivered
        except Exception as e:
            instance.delivery_status = DeliveryStatus.failed
        finally:
            instance.save()
            if message:
                existing_messages = APIMessage.objects.filter(external_id=message["id"]).exclude(
                    id=instance.id
                )
                if existing_messages:
                    existing_messages.delete()


@receiver(post_save, sender=Message)
def auto_respond_api(sender, **kwargs):
    created = kwargs["created"]
    instance = kwargs["instance"]
    if instance.delivery_status != DeliveryStatus.not_started:
        return
    enabled = instance.conversation.reservation.prop.organization.settings.chat_settings.enabled
    if enabled and created and not instance.outgoing:
        logger.debug("Attempting to auto-respond to API message")
        service = ChatService(instance)
        message = service.get_message()
        if message:
            final_message = "Hi {}\n\n{}\n\n{}".format(
                instance.conversation.reservation.guest.first_name,
                message,
                "Wayne, on behalf of Voyajoy",
            )
            APIMessage.objects.create(
                recipient=None,
                text=final_message,
                sender=None,
                outgoing=True,
                conversation=instance.conversation,
                # external_id=None,
                date_delivered=datetime.now(),
                delivery_status=DeliveryStatus.delivered,
            )
        else:
            logger.debug("Did not auto-respond to message")


# @receiver(post_save, send=SMSMessage)
# def auto_repond_sms(sender, **kwargs):
#     created = kwargs["created"]
#     auto_response_enabled = True
#     if auto_response_enabled and created:

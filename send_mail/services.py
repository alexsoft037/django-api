import logging

from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags

from notifications.services.sms import NexmoService, ServiceError
from rental_integrations.airbnb.service import AirbnbService

logger = logging.getLogger(__name__)


def send_sms(_from, to, text):
    service = NexmoService()
    service.send(
        _from=_from,
        to=to,
        text=text
    )


def send_email(_from, to, text, subject, attachments, **kwargs):
    html_content = text
    email = EmailMultiAlternatives(
        subject=subject,
        body=strip_tags(html_content),
        from_email=_from,
        to=(to,),
        attachments=attachments,
        **kwargs
    )
    email.attach_alternative(html_content, "text/html")
    try:
        email.send(fail_silently=False)
    except Exception as e:
        logger.info('error: {}'.format(e))
        raise ServiceError("Could not send message", e)


def send_airbnb_message(organization, external_id, text, attachments):
    app = organization.airbnbaccount_set.only("access_token", "user_id").last()
    service = AirbnbService(app.user_id, app.access_token)
    message = service.push_message(
        thread_id=external_id,
        message=text
    )
    return message


# def send_gmail_message():
#     html_content = validated_data["text"]
#
#     g_app = validated_data["organization"].googleapp_set.only("credentials").last()
#     google = Google(credentials=g_app.credentials)
#     response = google.send_message(
#         sender=getattr(validated_data["sender"], "email"),
#         to=getattr(validated_data["recipient"], "email"),
#         subject=validated_data["subject"],
#         message_text=strip_tags(html_content),
#     )
#     if response is None:
#         raise ValidationError("Could not send message")

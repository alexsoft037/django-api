import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import Membership
from notifications.models import Notification
from send_mail.models import Message

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Message)
def send_message_received_notification(sender, **kwargs):
    created = kwargs["created"]
    if created:
        instance = kwargs["instance"]
        incoming = not instance.outgoing
        if not incoming:
            return
        reservation = instance.conversation.reservation
        # date_created = instance.date_created
        recipient = instance.recipient
        org = instance.conversation.reservation.prop.organization
        content = instance.text
        user_id = Membership.objects.filter(
            organization=org,
            user_id=19
        ).values_list("user", flat=True).first()  # TODO FIX HACK
        # for user_id in user_ids:
        # TODO get users with permissions
        if user_id:
            Notification.objects.create(
                channel=Notification.Channels.Email.value,  # TODO
                content=f"{recipient.full_name} @ {reservation.prop.name}: {content}",
                to_id=user_id,
                content_object=instance,
            )
        else:
            logger.warning(f"Could not find user to send notification to id={user_id}")


# @receiver(post_save, sender=Property)
# def property_modified(sender, **kwargs):
#     created = kwargs["created"]
#     instance = kwargs["instance"]
#     full_address = instance.full_address
#     if created:
#         text = f"New property created: {full_address}"
#     else:
#         text = f"Property has been updated: {full_address}"
#     app = SlackApp.objects.get(organization=instance.organization)
#     client = SlackClient(app.access_token)
#     # TODO Temporary solution, move to services
#     client.api_call(
#         "chat.postMessage",
#         channel=app.channel,
#         text=text
#     )


# @receiver(post_save, sender=Message)
# def message_created(sender, **kwargs):
#     created = kwargs["created"]
#     instance = kwargs["instance"]
#     if not created:
#         return
#
#     text = f"New message (type={instance.type}) created: {instance.text}"
#     app = SlackApp.objects.get(organization=instance.prop.organization)
#     client = SlackClient(app.access_token)
#     # TODO Temporary solution, move to services
#     client.api_call(
#         "chat.postMessage",
#         channel=app.channel,
#         text=text
#     )

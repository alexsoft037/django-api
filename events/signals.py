import json
import logging
from functools import partial

from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import signals
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from accounts.models import Membership
from listings.models import Property, Reservation
from notifications.models import Notification
from notifications.services.slack import SlackMessageBuilder
from .choices import EventType
from .models import Event

logger = logging.getLogger(__name__)

# @receiver(post_save, sender=ListingDescriptions)
# @receiver(post_save, sender=BookingSettings)
# @receiver(post_save, sender=AvailabilitySettings)
# @receiver(post_save, sender=PricingSettings)
# @receiver(post_save, sender=Location)
# @receiver(post_save, sender=Rate)
# @receiver(post_save, sender=Discount)
# @receiver(post_save, sender=AdditionalFee)
# @receiver(post_save, sender=PointOfInterest)
# @receiver(post_save, sender=Image)
# @receiver(post_save, sender=Video)
# @receiver(post_save, sender=Room)
# @receiver(post_save, sender=Availability)
# @receiver(post_save, sender=BasicAmenities)
# @receiver(post_save, sender=HouseRules)
# @receiver(post_save, sender=Suitability)
# @receiver(post_save, sender=Blocking)
# @receiver(post_save, sender=TurnDay)
# @receiver(post_save, sender=SchedulingAssistant)


@receiver(post_delete, sender=Property)
@receiver(post_delete, sender=Reservation)
# @receiver(post_save, sender=get_user_model())
def model_deleted(sender, instance, **kwargs):
    if not instance.request_user:
        return
    context = {"request_user_id": instance.request_user.id}
    EventLog = partial(
        Event,
        content_object=instance,
        user=instance.request_user,
        organization=instance.organization,
        context=context,
        event_type=EventType.Model_deleted,
    )
    EventLog().save()


@receiver(post_save, sender=Property)
@receiver(post_save, sender=Reservation)
# @receiver(post_save, sender=get_user_model())
def model_saved(sender, created, instance, **kwargs):
    if not instance.request_user:
        return
    EventLog = partial(
        Event,
        content_object=instance,
        user=instance.request_user,
        organization=instance.organization,
    )
    context = {"request_user_id": instance.request_user.id}
    if created:
        EventLog(event_type=EventType.Model_created, context=context).save()
    else:
        context.update(instance._updated_fields())
        data = json.dumps(context, sort_keys=True, cls=DjangoJSONEncoder)
        EventLog(event_type=EventType.Model_modified, context=json.loads(data)).save()


if apps.is_installed("send_mail"):

    @receiver(signals.post_save, sender="send_mail.Message")
    def message_created(sender, created, instance, **kwargs):
        if not created:
            return

        event_type = EventType.Message_sent if instance.outgoing else EventType.Message_received
        Event.objects.create(
            event_type=event_type,
            content_object=instance.conversation,
            context={"send_mail.Message": instance.pk},
        )


# @receiver(signals.post_save, sender=Reservation)
# def reservation_saved(sender, created, instance, **kwargs):
#     if created:
#         user_id = instance.request_user.id
#         context = {"request_user_id": user_id}
#
#         ReservationEvent = partial(
#             Event,
#             content_object=instance,
#             context=context,
#             organization=instance.prop.organization,
#         )
#
#         if instance.is_inquiry:
#             ReservationEvent(event_type=EventType.Inquiry).save()
#         else:
#             ReservationEvent(event_type=EventType.Reservation_created).save()
#
#     reservation_changed.send(sender=sender, changes=instance._changed_fields(), instance=instance)  # noqa: E501


def create_notifications(events):
    for event in events:
        instance = event.content_object
        org = instance.prop.organization
        user_id = (
            Membership.objects.filter(organization=org, user_id=19)
            .values_list("user", flat=True)
            .first()
        )  # TODO FIX HACK
        # for user_id in user_ids:
        # TODO get users with permissions
        if user_id:
            builder = SlackMessageBuilder()
            if event.event_type == EventType.Reservation_modified.value:
                data = builder.get_reservation_update_message(instance)
            elif event.event_type == EventType.Reservation_cancelled.value:
                data = builder.get_reservation_cancellation_message(instance)
            elif event.event_type == EventType.Reservation_created.value:
                data = builder.get_reservation_created_message(instance)
            else:
                continue
            Notification.objects.create(
                channel=Notification.Channels.Slack.value,
                content_data=data,
                to_id=user_id,
                content_object=instance,
            )
        else:
            logger.warning(f"Could not find user to send notification to id={user_id}")


# @receiver(reservation_changed, sender=Reservation)
# def reservation_changed_handler(sender, changes: dict, instance: Reservation, **kwargs):
#     ReservationEvent = partial(
#         Event, content_object=instance, organization=instance.prop.organization
#     )
#     events = []
#
#     user_id = instance.request_user.id
#
#     if instance.is_inquiry and instance.send_email and instance.guest and instance.guest.email:
#         send_inquiry_email(instance)
#         events.append(
#             ReservationEvent(
#                 event_type=EventType.Quote_sent,
#                 context={"request_user_id": user_id},
#             )
#         )
#
#     if "private_note" in changes:
#         events.append(
#             ReservationEvent(
#                 event_type=EventType.Notes_changed,
#                 context={"request_user_id": user_id},
#             )
#         )
#
#     if "status" in changes and instance.status == Reservation.Statuses.Accepted.value:
#         events.append(
#             ReservationEvent(
#                 event_type=EventType.Reservation_created,
#                 context={"request_user_id": user_id},
#             )
#         )
#
#     if "status" in changes and instance.status == Reservation.Statuses.Cancelled.value:
#         events.append(
#             ReservationEvent(
#                 event_type=EventType.Reservation_cancelled,
#                 context={"request_user_id": user_id},
#             )
#         )
#
#     reservation_changes = {
#         "start_date",
#         "end_date",
#         "price",
#         "guests_adults",
#         "guests_children",
#         "guests_infants",
#         "pets",
#         "guest",
#         "rebook_allowed_if_cancelled",
#     }
#     if changes.keys() & reservation_changes:
#         events.append(
#             ReservationEvent(
#                 event_type=EventType.Reservation_modified,
#                 context={"request_user_id": user_id},
#             )
#         )
#
#     if "payment" in changes:
#         events.append(
#             ReservationEvent(
#                 event_type=EventType.Payment,
#                 context={
#                     "amount": changes["payment"],
#                     "request_user_id": user_id,
#                 },
#             )
#         )
#
#     if "refund" in changes:
#         events.append(
#             ReservationEvent(
#                 event_type=EventType.Refund,
#                 context={"amount": changes["refund"], "request_user_id": user_id},
#             )
#         )
#
#     Event.objects.bulk_create(events)
#     create_notifications(events)


EVENT_NOTIFICATION_TEXT = {"start_date": "", "end_date": "", "status": "", "private_note": ""}

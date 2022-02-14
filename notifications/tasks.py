import datetime as dt
import logging

import requests
from celery import group
from celery.task import periodic_task, task

from app_marketplace.models import SlackApp
from listings.models import Reservation
from notifications.models import Notification
from notifications.services.sms import NexmoService
from send_mail.models import Message
from vendors.models import Job, Vendor
from . import models


logger = logging.getLogger(__name__)


@periodic_task(run_every=dt.timedelta(seconds=60))
def collect_notifications():
    ids = models.Notification.objects.filter(is_sent=False).values_list("id", flat=True)
    job = group(send_notification.s(id) for id in ids)
    job.apply_async()
    return "Scheduled notification to be send"


@task
def send_notification(notification_id):
    try:
        # check if not sent and if hasn't been trieed
        instance = models.Notification.objects.get(pk=notification_id)
        if instance.is_sent:
            return
        content = instance.content
        channel = instance.channel
        content_object = instance.content_object
        user = instance.to
        if isinstance(content_object, Message):
            org = content_object.conversation.reservation.prop.organization
        elif isinstance(content_object, Reservation) or isinstance(content_object, Job):
            org = content_object.prop.organization
        elif isinstance(content_object, Vendor):
            org = content_object.user.organization
        else:
            org = content_object.organization

        if channel == Notification.Channels.SMS.value:
            nexmo_service = NexmoService()
            nexmo_service.perform_send(
                to=user.phone,
                text=content
            )
        else:
            app = SlackApp.objects.get(organization=org)

            webhook_url = app.url
            data = instance.content_data
            response = requests.post(
                webhook_url,
                json=data,
            )
            if not response.ok:
                logger.error(f"Not able to send slack notification for user={instance.to_id}")
        instance.is_sent = True
        instance.save()
    except models.Notification.DoesNotExist:
        pass

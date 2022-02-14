from contextlib import suppress

from django.conf import settings
from django.db.models import F
from django.db.models.functions import Lower
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from notifications.models import Notification
from vendors.mapping import STATUS_TO_EVENT
from vendors.templates import MESSAGE_NEW_JOB, MESSAGE_NEW_ACCOUNT
from .models import Job, Report, WorkLog, Vendor


@receiver(post_save, sender=Job)
def notify_status_change_post(sender, instance, created, **kwargs):
    update_fields = kwargs["update_fields"]
    if created or (update_fields and "status" in update_fields):
        WorkLog.objects.create(
            job=instance, event=STATUS_TO_EVENT.get(Job.Statuses(instance.status)).value
        )


@receiver(pre_save, sender=Job)
def notify_status_change(sender, instance, **kwargs):
    with suppress(Job.DoesNotExist):
        old_data = Job.objects.filter(pk=instance.pk).values("status").first()
        if old_data and old_data["status"] != instance.status:
            WorkLog.objects.create(
                job=instance, event=STATUS_TO_EVENT.get(Job.Statuses(instance.status)).value
            )


@receiver(post_save, sender=Report)
def notify_report(sender, instance, created, **kwargs):
    # prop = instance.job.prop
    if created:
        event = WorkLog.Event.Problem if instance.is_problem else WorkLog.Event.Contact
        WorkLog.objects.create(job=instance.job, event=event.value)


def _send_new_job_notification(instance):
    assignee = instance.assignee
    prop = instance.prop
    date = instance.time_frame.lower
    WorkLog.objects.create(job=instance, event=WorkLog.Event.Reassign.value)
    Notification.objects.create(
        channel=Notification.Channels.SMS.value,  # TODO
        content=MESSAGE_NEW_JOB.format(
            name=prop.organization.name,
            app_name=settings.APP_NAME,
            fee=f"${instance.base_cost}",
            date=date.strftime("%b %d, %Y @ %I%p"),
            link=settings.COZMO_WEB_URL,
        ),
        to_id=assignee.user.id,
        content_object=instance,
    )


@receiver(pre_save, sender=Job)
def notify_assignee_change(sender, instance, **kwargs):
    with suppress(Job.DoesNotExist):
        old_data = (
            Job.objects.filter(pk=instance.pk)
            .annotate(start_date=Lower("time_frame"))
            .values("status", "assignee_id", "start_date", place=F("prop__name"))
            .first()
        )
        if old_data and old_data["assignee_id"] != instance.assignee.id:
            _send_new_job_notification(instance)


@receiver(post_save, sender=Job)
def notify_job(sender, instance, **kwargs):
    created = kwargs["created"]
    if created:
        _send_new_job_notification(instance)


@receiver(post_save, sender=Vendor)
def notify_new_vendor(sender, instance, **kwargs):
    Notification.objects.create(
        channel=Notification.Channels.SMS.value,  # TODO
        content=MESSAGE_NEW_ACCOUNT.format(
            name=instance.invited_by.first_name,
            company=instance.invited_by.organization.name,
        ),
        to_id=instance.user.id,
        content_object=instance,
    )

import datetime as dt
import logging

from celery import group
from celery.exceptions import Ignore
from celery.task import periodic_task, task
from django.core.exceptions import MultipleObjectsReturned
from django.db.models.expressions import F
from django.db.models.functions import Lower, Upper
from django.utils import timezone
from psycopg2._range import DateTimeTZRange

from listings.models import Reservation, SchedulingAssistant
from notifications.models import Notification
from . import models

logger = logging.getLogger(__name__)


@periodic_task(run_every=dt.timedelta(days=1))
def create_clean_jobs():
    now = timezone.now()
    reservations = Reservation.objects.filter(
        end_date__gte=now, end_date__lte=now + dt.timedelta(days=7)
    ).values("prop_id", "end_date")

    job = group(create_clean_job.s(**res) for res in reservations)
    job.apply_async()
    return "Scheduled clean job creation"


@task
def create_clean_job(prop_id, end_date):
    start = dt.datetime.strptime(f"{end_date}T00:00", "%Y-%m-%dT%H:%M")
    end = dt.datetime.strptime(f"{end_date}T23:59", "%Y-%m-%dT%H:%M")
    time_frame = DateTimeTZRange(start, end)

    scheduling_a = SchedulingAssistant.objects.get(prop=prop_id)
    if not scheduling_a.automatically_assign:
        raise Ignore(f"Clean job for {end_date} in property {prop_id}, automatically_assign=False")

    assignment = (
        models.Assignment.objects.filter(prop_id=prop_id, order__gte=1)
        .values(assignee_id=F("vendor_id"), base_cost=F("cleaning_fee"))
        .order_by("order")
        .first()
    )
    if not assignment:
        raise Ignore(f"Clean job for {end_date} in property {prop_id}, no assignment")

    try:
        _, created = models.Job.objects.filter(time_frame__overlap=time_frame).get_or_create(
            prop_id=prop_id,
            job_type=models.Job.Jobs.Clean.value,
            defaults={
                "time_estimate": scheduling_a.time_estimate,
                "time_frame": time_frame,
                **assignment,
            },
        )
    except MultipleObjectsReturned:
        created = False

    if not created:
        raise Ignore(f"Clean job for {end_date} in property {prop_id} already exists")

    return f"Created clean job for {end_date} in property {prop_id}"


REMINDER_MINUTES = 30


@periodic_task(run_every=dt.timedelta(minutes=REMINDER_MINUTES))
def notify_upcoming_job():
    now = timezone.now() + dt.timedelta(hours=6)
    start = dt.datetime.combine(now, dt.time(now.hour, 0, tzinfo=now.tzinfo))
    end = start + dt.timedelta(minutes=REMINDER_MINUTES)
    day = dt.timedelta(days=1)

    qs = (
        models.Job.objects.filter(is_active=True)
        .exclude(
            status__in=(
                models.Job.Statuses.Completed.value,
                models.Job.Statuses.Cancelled.value,
                models.Job.Statuses.In_Progress.value,
            )
        )
        .annotate(start=Lower("time_frame"), to_id=F("assignee_id"), place=F("prop__name"))
    )

    for before in (0, 1, 3):
        Notification.objects.bulk_create(
            Notification(
                channel=Notification.Channels.SMS.value,
                content="You have upcoming job in property {} in {} day(s).".format(
                    job.place, before
                ),
                to_id=job.to_id,
                content_object=job,
            )
            for job in qs.filter(start__contained_by=(start + before * day, end + before * day))
        )

    return "Job reminders scheduled"


@periodic_task(run_every=dt.timedelta(minutes=REMINDER_MINUTES))
def notify_missed_job():
    now = timezone.now()

    qs = (
        models.Job.objects.exclude(
            is_active=False,
            status__in=(
                models.Job.Statuses.Completed.value,
                models.Job.Statuses.Cancelled.value,
                models.Job.Statuses.In_Progress.value,
            ),
        )
        .annotate(
            start=Lower("time_frame"),
            end=Upper("time_frame"),
            place=F("prop__name"),
            to_id=F("assignee_id"),
        )
        .filter(
            time_frame__overlap=(now, now + dt.timedelta(hours=REMINDER_MINUTES)),
            time_estimate__gt=F("end") - now,
        )
    )

    Notification.objects.bulk_create(
        Notification(
            channel=Notification.Channels.SMS.value,
            content="Check in to property {}. Job should end before {}.".format(
                job.place, job.end.strftime("%Y-%m-%d %H:%M %Z")
            ),
            to_id=job.to_id,
            content_object=job,
        )
        for job in qs
    )

    return "Job check in remainders scheduled"

from datetime import timedelta
from logging import getLogger

from celery import group
from celery.task import periodic_task, task
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from send_mail.choices import Status
from send_mail.models import ParseEmailTask
from send_mail.serializers import ParseEmailSerializer

logger = getLogger(__name__)


@periodic_task(run_every=timedelta(minutes=5))
def queue_parse_email_tasks():
    if not settings.PARSE_EMAIL_ENABLED:
        return "Parse email task queueing job is not enabled. Skipping"
    tasks = ParseEmailTask.objects.filter(status=Status.init)
    task_ids = list(tasks.values_list("id", flat=True))
    tasks.update(status=Status.queue.value)
    job = group(parse_email.s(pk) for pk in task_ids)
    job.apply_async()
    return "Completed parse email task queueing job"


@task
def parse_email(task_id):
    """
    Parsing supported emails can perform the following actions
     - Create reservations, inquiries, and pending reservations if it does not exist
     - Create messages and associate them with reservations
     - Record cancellations, but not refunds.
     - Update guest avatars if available
     - Update the confirmation code if not set or not matching
    Limitations
     - Will not attempt to make changes if the expected initial email is not received?
     - Cannot record changes to a reservation because Airbnb does not report that information
     - Refunds may be handled in the future
    """
    t = ParseEmailTask.objects.get(id=task_id)
    if t.status == Status.completed.value:
        return f"Parse email task has already been completed"
    t.status = Status.started.value
    t.save()
    serializer = ParseEmailSerializer(data=t.data)
    try:
        serializer.is_valid(raise_exception=True)
        message = serializer.save()
        t.content_object = message
        t.status = Status.completed.value
        t.error = ""
        t.save()
    except Exception as e:
        t.status = Status.error.value
        t.error = str(e)
        t.save()
    return f"Parsed email (id={task_id})"


@periodic_task(run_every=timedelta(days=1))
def clean_parse_email_tasks():
    if not settings.PARSE_EMAIL_ENABLED:
        return "Parse email task cleaning job is not enabled. Skipping"
    target_date = timezone.now() - settings.PARSE_EMAIL_TASK_DB_TTL
    ParseEmailTask.objects.filter(
        Q(status=Status.completed) | Q(date_created__lte=target_date)
    ).delete()
    return "Completed clean parse email task queueing job"

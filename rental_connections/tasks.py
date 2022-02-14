from datetime import timedelta
from logging import getLogger

from celery import group
from celery.exceptions import Ignore
from celery.task import task
from django.utils import timezone

from listings.tasks import fetch_property_media
from .models import RentalConnection, SyncLog

logger = getLogger(__name__)
UPDATE_EACH = timedelta(hours=8)


# @periodic_task(run_every=timedelta(minutes=15))
def rental_connections_sync():
    needs_update = timezone.now() - UPDATE_EACH
    pks = RentalConnection.objects.filter(
        date_updated__lt=needs_update, status=RentalConnection.Statuses.Enabled
    ).values_list("id", flat=True)
    job = group(rental_connection_sync.s(pk, False) for pk in pks)
    job.apply_async()
    return "Scheduled connections update"


@task
def rental_connection_sync(connection_id, initial):
    try:
        conn = RentalConnection.objects.get(id=connection_id)
    except RentalConnection.DoesNotExist:
        raise Ignore(f"Connection id={connection_id} does not exist")

    if initial:
        sync = conn._sync_initial
    else:
        sync = conn._sync_update

    try:
        sync()
        media_job = group(
            fetch_property_media.s(pk) for pk in conn.property_set.values_list("id", flat=True)
        )
        media_job.apply()
    except Exception as e:
        logger.warning("Connection sync failed: id=%s, error=%s", connection_id, e.args)
        conn.log(SyncLog.Statuses.Error)
    else:
        conn.log(SyncLog.Statuses.Synced)
    conn.save()  # so conn.date_update will be updated

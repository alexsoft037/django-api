import datetime as dt
import logging

from celery import group
from celery.exceptions import Ignore
from celery.task import periodic_task, task
from django.utils import timezone

from .models import ExternalCalendar, SyncLog

logger = logging.getLogger(__name__)
UPDATE_EACH = dt.timedelta(hours=3)


@periodic_task(run_every=dt.timedelta(minutes=15))
def fetch_calendars():
    now = timezone.now()
    needs_update = now - UPDATE_EACH
    pks = ExternalCalendar.objects.filter(date_updated__lt=needs_update, enabled=True).values_list(
        "id", flat=True
    )

    logger.info("Calendars Sync Task starts on {} Calendars to sync ids: {} ".format(now, pks))

    job = group(fetch_calendar.s(pk) for pk in pks)
    job.apply_async()
    return "Scheduled calendars update"


@task
def fetch_calendar(pk):
    try:
        cal = ExternalCalendar.objects.get(pk=pk)
        cal.fetch()
    except ExternalCalendar.DoesNotExist:
        info = "Calendar id={} does not exist".format(pk)
        logger.info(info)
        raise Ignore(info)
    except ValueError:
        ok = False
        ret_info = "Could not connect to calendar id={}".format(pk)
        logger.warning(ret_info)
    else:
        ok = True
        ret_info = "Calendar id={} synced".format(pk)

    cal.save()
    SyncLog.objects.create(calendar=cal, success=ok, events=cal.events_count)

    return ret_info

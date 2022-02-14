from datetime import datetime, timedelta
from logging import getLogger

from celery import group
from celery.task import periodic_task, task
from django.conf import settings
from django.db.models import Q

from accounts.profile.models import PlanSettings
from listings.models import Property
from rental_integrations.trip_advisor.models import TripAdvisorSync
from rental_integrations.trip_advisor.service import TripAdvisorClient

logger = getLogger(__name__)


def get_jobs(partial=False):
    plans = PlanSettings.objects.filter(trip_advisor_sync=True)
    now = datetime.now()
    jobs = []
    for plan in plans:
        property_ids = Property.objects.filter(
            Q(organization=plan.organization),
            (
                (
                    Q(
                        tripadvisor__sync_enabled=True,
                        tripadvisor__last_sync__lte=now - timedelta(hours=12),
                    )
                )
                | Q(tripadvisor=None)
            ),
        ).values_list("id", flat=True)
        jobs.append(update_or_create_listings.s(property_ids, partial))
    return jobs


@periodic_task(run_every=timedelta(hours=12))
def full_update_or_create_listings():
    tasks_group = group(get_jobs())
    tasks_group.apply_async()
    return "TripAdvisor Full update"


@periodic_task(run_every=timedelta(hours=3))
def update_listings():
    tasks_group = group(get_jobs(True))
    tasks_group.apply_async()
    return "TripAdvisor Partial update"


@task
def update_or_create_listings(ids, partial=False):
    client = TripAdvisorClient(settings.TRIPADVISOR_CLIENT_ID, settings.TRIPADVISOR_SECRET_KEY)
    now = datetime.now()
    properties = Property.objects.filter(id__in=ids)
    for prop in properties:
        status = None

        try:
            status, _ = client.push_listing(prop, partial)
        except ValueError as e:
            logger.warning("Could not Sync property id: %s, exception: ", prop.id, e)

        if status == 200:
            if hasattr(prop, "tripadvisor"):
                prop.tripadvisor.last_sync = now
                prop.tripadvisor.save()
            else:
                TripAdvisorSync.objects.create(
                    prop=prop, organization=prop.organization, last_sync=now, sync_enabled=True
                )
            logger.info("Property synced id: %s", prop.id)
        else:
            logger.warning("Could not Sync property id: %s", prop.id)

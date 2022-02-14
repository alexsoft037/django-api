from datetime import timedelta
from logging import getLogger

from celery import group
from celery.exceptions import Ignore
from celery.task import periodic_task, task
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from accounts.profile.models import PlanSettings
from listings.models import Property
from .models import BookingAccount, BookingSync, Listing
from .service import BookingXmlClient

logger = getLogger(__name__)


@periodic_task(run_every=timedelta(seconds=60))
def fetch_reservations():
    if settings.ENV_TYPE in ("test", "sandbox", "dev"):
        raise Ignore("Fetching booking.com reservations only on prodution")

    account = BookingAccount.objects.filter(user_id=settings.BOOKING_USERNAME).first()
    if account is None:
        raise Ignore("No account with username {}".format(settings.BOOKING_USERNAME))

    account.update_reservations(secret=settings.BOOKING_CLIENT_SECRET)
    account.import_reservations()

    # FIXME This is walkaround for propagating new reservations to all booking accounts
    listings_data = [*account.listing_set.values_list("data", flat=True).iterator()]
    job = group(
        nasty_walkaround.s(vals["id"], listings_data)
        for vals in BookingAccount.objects.filter(user_id=settings.BOOKING_USERNAME)
        .exclude(pk=account.pk)
        .values("id")
    )
    job.apply_async()

    return "Updated reservations for BookingAccount id={}".format(account.id)


@task(name="Nasty walkaround for booking.com sandbox")
def nasty_walkaround(account_id, listings_data):
    try:
        account = BookingAccount.objects.get(id=account_id)
    except BookingAccount.DoesNotExist:
        raise Ignore("Booking account {} no longer exists".format(account_id))

    account.listing_set.all().delete()
    account.listing_set.bulk_create(Listing(owner=account, data=data) for data in listings_data)
    account.import_reservations()

    return "Updated reservations for BookingAccount id={}".format(account.id)


def get_jobs(partial=False):
    plans = PlanSettings.objects.filter(booking_sync=True).only("organization_id")
    now = timezone.now()

    def prop_ids(plan):
        return Property.objects.filter(
            Q(organization=plan.organization),
            (
                Q(booking__sync_enabled=True, booking__last_sync__lte=now - timedelta(hours=12))
                | Q(booking=None)
            ),
        ).values_list("id", flat=True)

    return [update_or_create_listings.s(list(prop_ids(plan)), partial) for plan in plans]


@periodic_task(run_every=timedelta(hours=12))
def full_update_or_create_listings():
    tasks_group = group(get_jobs())
    tasks_group.apply_async()
    return "Booking.com Full update"


@periodic_task(run_every=timedelta(hours=3))
def update_listings():
    tasks_group = group(get_jobs(partial=True))
    tasks_group.apply_async()
    return "Booking.com Partial update"


@task
def update_or_create_listings(ids, partial=False):
    client = BookingXmlClient(settings.BOOKING_CLIENT_ID, settings.BOOKING_CLIENT_SECRET)
    now = timezone.now()

    for prop in Property.objects.filter(id__in=ids).iterator():
        try:
            status, content = client.push_listing(prop, partial)
        except ValueError as e:
            status = None
            logger.warning("Could not Sync property id: %s, exception: ", prop.id, e)

        if status == 200:
            booking = getattr(
                prop,
                "booking",
                BookingSync(
                    prop=prop,
                    external_id=content["id"],
                    organization=prop.organization,
                    sync_enabled=True,
                ),
            )
            booking.last_sync = now
            booking.save()
            logger.info("Property synced id: %s", prop.id)
        else:
            logger.warning("Could not Sync property id: %s", prop.id)

from datetime import timedelta
from logging import getLogger

from celery import group
from celery.exceptions import Ignore
from celery.task import periodic_task, task
from django.conf import settings

from listings.models import Property
from rental_network.apartments.service import ApartmentsRentalNetworkClient
from rental_network.models import Account, Listing, ProxyAssignment, RentalNetworkJob
from rental_network.serializers import (CozmoListingToApartmentsSerializer,
                                        CozmoListingToZillowSerializer, ScreenshotSerializer)
from rental_network.signals import _get_proxy
from rental_network.zillow.service import ZillowRentalNetworkClient

logger = getLogger(__name__)
UPDATE_EACH = timedelta(hours=8)


# @periodic_task(run_every=timedelta(minutes=15))
# def sync_listing_status():
#     accounts = Account.objects.all()
#     for account in accounts:
#         listing_ids = account.listing_set.exclude(status__in=[
#             Listing.Status.INIT,
#             Listing.Status.ERROR,
#             Listing.Status.DELISTED,
#             Listing.Status.DELETED,
#         ]).values_list("external_id", flat=True)


@periodic_task(run_every=timedelta(minutes=15))
def rental_network_run_queue():
    if not settings.LONG_TERM_CHANNELS_ENABLED:
        return
    pks = RentalNetworkJob.objects.filter(status=RentalNetworkJob.Status.INIT.value).values_list(
        "id", flat=True
    )
    job = group(rental_network_worker.s(pk) for pk in pks)
    job.apply_async()
    return "Scheduled rental network update"


@periodic_task(run_every=timedelta(minutes=15))
def create_new_rental_network():
    if not settings.LONG_TERM_CHANNELS_ENABLED:
        return
    properties = Property.objects.filter(channel_network_enabled=True)
    for instance in properties:
        if (
            instance.organization.settings.channel_network_enabled
            and not instance.rental_network_jobs.exists()
        ):
            accounts = Account.objects.filter(organization=instance.organization)
            for account in accounts:
                proxy_assignment = ProxyAssignment.objects.filter(account=account, prop=instance)
                if not proxy_assignment.exists():
                    proxy_assignment = ProxyAssignment.objects.create(
                        account=account, prop=instance, proxy=_get_proxy()
                    )
                else:
                    proxy_assignment = proxy_assignment[0]
                RentalNetworkJob.objects.get_or_create(
                    status=RentalNetworkJob.Status.INIT,
                    job_type=RentalNetworkJob.Type.CREATE,
                    prop=instance,
                    proxy=proxy_assignment.proxy,
                    account=account,
                )
    return "Scheduled rental network create"


def _save_screenshots(service, job_id):
    photos = list()
    for each in service.screenshots:
        # with open(f"/tmp/{str(uuid.uuid4())}.png", "wb") as f:
        #     f.write(each)
        data = {"image": each, "caption": "", "job": job_id}
        photos.append(data)
    serializer = ScreenshotSerializer(data=photos, many=True)
    if serializer.is_valid():
        serializer.save()


def _create(job):
    """
    TODO test to see if it needs to be created
    :param job:
    :return:
    """
    logger.info(f"found job={job}")
    prop = job.prop
    account = job.account
    assignment = job.account.proxyassignment_set.first()
    logger.info(f"using {account}, {assignment}")
    account_class = {
        Account.AccountType.ZILLOW.value: ZillowRentalNetworkClient,
        Account.AccountType.APARTMENTS.value: ApartmentsRentalNetworkClient,
    }.get(account.account_type)
    service = account_class(
        user=account.username, secret=account.password, proxy=assignment.proxy.url
    )
    logger.info(f"service {service}")

    serializer_class = {
        Account.AccountType.ZILLOW.value: CozmoListingToZillowSerializer,
        Account.AccountType.APARTMENTS.value: CozmoListingToApartmentsSerializer,
    }.get(account.account_type)
    serializer = serializer_class(instance=job.prop)
    listing_type = {
        Account.AccountType.ZILLOW.value: Listing.Type.ZILLOW,
        Account.AccountType.APARTMENTS.value: Listing.Type.APARTMENTS,
    }.get(account.account_type)
    listing, created = Listing.objects.get_or_create(
        prop=prop, organization=prop.organization, listing_type=listing_type, account=account
    )
    try:
        listing.status = Listing.Status.UPDATING.value
        listing.save()
        listing_id = service.create_listing(serializer.data)
        listing.external_id = listing_id
        listing.status = Listing.Status.SUBMITTED
        listing.save()
        # service.get_listings()
    except Exception as ee:
        listing.status = Listing.Status.ERROR
        listing.save()

    _save_screenshots(service, job.pk)
    job.status = RentalNetworkJob.Status.COMPLETED.value
    logger.info(f"saving {job.status}")
    job.save()


def _update(job):
    logger.info(f"found job={job}")
    prop = job.prop
    account = job.account
    assignment = job.account.proxyassignment_set.first()
    logger.info(f"using {account}, {assignment}")
    account_class = {
        Account.AccountType.ZILLOW.value: ZillowRentalNetworkClient,
        Account.AccountType.APARTMENTS.value: ApartmentsRentalNetworkClient,
    }.get(account.account_type)
    service = account_class(
        user=account.username, secret=account.password, proxy=assignment.proxy.url
    )
    logger.info(f"service {service}")

    serializer_class = {
        Account.AccountType.ZILLOW.value: CozmoListingToZillowSerializer,
        Account.AccountType.APARTMENTS.value: CozmoListingToApartmentsSerializer,
    }.get(account.account_type)
    serializer = serializer_class(instance=job.prop)
    listing_type = {
        Account.AccountType.ZILLOW.value: Listing.Type.ZILLOW,
        Account.AccountType.APARTMENTS.value: Listing.Type.APARTMENTS,
    }.get(account.account_type)
    listing = Listing.objects.get(
        prop=prop, organization=prop.organization, listing_type=listing_type
    )
    try:

        service.update_listing(listing.external_id, serializer.data)
    except Exception as ee:

        listing.status = Listing.Status.ERROR
        listing.save()
    _save_screenshots(service, job.pk)


def _delete(job):
    pass


@task
def rental_network_worker(job_id):
    if not settings.LONG_TERM_CHANNELS_ENABLED:
        return
    # change to create
    logger.info(f"starting rental network worker {job_id}")
    try:
        job = RentalNetworkJob.objects.get(pk=job_id)
    except RentalNetworkJob.DoesNotExist:
        raise Ignore(f"Connection id={job_id} does not exist")

    task = {
        RentalNetworkJob.Type.CREATE.value: _create,
        RentalNetworkJob.Type.UPDATE.value: _update,
        RentalNetworkJob.Type.DELETE.value: _delete,
    }.get(job.job_type)
    try:
        job.status = RentalNetworkJob.Status.STARTED.value
        job.save()
        task(job)
        job.status = RentalNetworkJob.Status.COMPLETED.value
        logger.info(f"saving {job.status}")
        job.save()
    except Exception as e:
        job.status = RentalNetworkJob.Status.ERROR.value
        logger.debug(f"error={e}")
    finally:
        job.save()

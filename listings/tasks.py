from contextlib import contextmanager
from datetime import timedelta
from hashlib import md5
from io import BytesIO
from itertools import chain
from logging import getLogger
from os.path import splitext
from urllib.parse import urlparse

import requests
from celery import group
from celery.task import periodic_task, task
from django.db.models import DateField
from django.db.models.expressions import ExpressionWrapper, F
from django.utils import timezone

from listings.models import Property
from payments.services import Stripe, StripeError
from services.errors import ServiceError
from services.google import GoogleService
from . import models
from .choices import SecurityDepositTypes

logger = getLogger(__name__)


@contextmanager
def ignored(*exceptions, log_message="%s"):
    try:
        yield
    except exceptions as e:
        logger.info(log_message, e.__class__.__name__)


@task
def fetch_property_media(prop_id):
    images = models.Image.objects.filter(prop_id=prop_id).externally_hosted()
    videos = models.Video.objects.filter(prop_id=prop_id).externally_hosted()

    for media in chain(images, videos):
        message = f"Error fetching media: %s url={media.url}"
        with ignored(
            requests.ConnectionError,
            requests.HTTPError,
            requests.RequestException,
            log_message=message,
        ):
            resp = requests.get(media.url, stream=True, timeout=5)
            resp.raise_for_status()
            url = urlparse(media.url.url)
            name = "{name}.{ext}".format(
                name=md5(url.path.encode()).hexdigest(), ext=splitext(url.path)[-1]  # nosec
            )
            media.url.save(name, BytesIO(resp.content))


@periodic_task(run_every=timedelta(hours=6))
def reservation_deposit_refund():
    today = timezone.now().today()
    payment_service = Stripe()

    release_date = ExpressionWrapper(F("end_date") + F("refund_deposit_after"), DateField())
    refunded = []

    for reservation in (
        models.Reservation.objects.exclude(refund_deposit_after=None)
        .annotate(release_date=release_date)
        .filter(release_date=today)
        .only("id", "payments")
    ):
        security_deposits = reservation.reservationfee_set.filter(
            refundable=True, fee_tax_type=SecurityDepositTypes.Security_Deposit.value
        )
        total_deposit = security_deposits.aggregate(total=models.Sum("amount"))["total"]

        if not total_deposit:
            continue

        refundable = reservation.payments.annotate(
            currently_paid=F("amount") - F("refunded_amount")
        ).filter(currently_paid__gt=0)
        for charge in refundable:
            to_refund = min(total_deposit, charge.currently_paid)
            try:
                payment_service.refund(charge.external_id, int(to_refund * 100))
            except StripeError as e:
                logger.warning("Could not refund charge id: %s, %s", charge.id, e)
                continue

            charge.refunded_amount += to_refund
            charge.save()

            total_deposit -= to_refund
            if total_deposit == 0:
                break

        security_deposits.update(refundable=False)
        refunded.append(reservation.id)

    return "Deposit refunded for reservations: {}".format(refunded)


@periodic_task(run_every=timedelta(minutes=15))
def queue_time_zone_jobs():
    properties = (
        Property.objects.filter(time_zone="")
        .exclude(location__latitude=None, location__longitude=None)
        .values_list("pk", flat=True)
    )
    job = group(set_time_zone.s(pk) for pk in properties)
    job.apply_async()
    return "Scheduled timezone jobs"


@task
def set_time_zone(pk):
    prop = Property.objects.get(pk=pk)
    location = prop.location
    try:
        service = GoogleService()
        tz = service.get_timezone(location.latitude, location.longitude)
        prop.time_zone = tz
    except ServiceError:
        prop.time_zone = None
    finally:
        prop.save()

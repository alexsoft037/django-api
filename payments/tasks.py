from logging import getLogger

from celery.exceptions import Ignore
from celery.task import task

from payments.models import Coupon
from payments.serializers import CouponSerializer, DisputeSerializer
from payments.services import Stripe

logger = getLogger(__name__)


@task
def disputes_sync(after):
    resp = Stripe().list_after_disputes(after)
    serializer = DisputeSerializer(data=resp, many=True)

    if not serializer.is_valid():
        raise Ignore(f"Dispute validation error id: {resp.id}")
    serializer.save()
    return "Disputes Synced"


@task
def coupon_sync():
    stripe = Stripe()
    coupons = stripe.list_after_coupons()
    # deleting already not existing coupons
    Coupon.objects.exclude(external_id__in=map(lambda c: c.id, coupons)).delete()

    serializer = CouponSerializer(data=coupons, many=True)
    if not serializer.is_valid():
        raise Ignore(f"Coupon validation error: {serializer.errors}")
    serializer.save()
    return "Coupons Synced"

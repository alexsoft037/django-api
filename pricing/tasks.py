import logging
from datetime import timedelta

from celery.task import task
from django.conf import settings

from cozmo_common.utils import get_today_date
from listings.models import Property, Rate
from services.pricing import PricingService

logger = logging.getLogger(__name__)


"""
Once a day, perform pricing changes. Order of priority from least to greatest
 - nightly pricing
 - weekly/monthly pricing
 - suggested pricing
 - weekly pricing
 - same day pricing
Send signal to Airbnb to make changes

"""

# @periodic_task(run_every=timedelta(days=1))
# def queue_pricing_tasks():
#     pass


def _generate_dates(days_delta):
    days = list()
    # FIX HACK
    today = get_today_date("America/Los_Angeles")
    for x in range(0, days_delta):
        days.append(today + timedelta(days=x))
    return days


@task
def generate_smart_pricing(pk):
    prop = Property.objects.get(pk=pk)
    # Rate.objects.filter(prop_id=pk, smart=True).delete()
    dates = _generate_dates(getattr(settings, "DEFAULT_SMART_PRICING_DAYS", 90))
    service = PricingService(prop)
    for d in dates:
        price = service.get_price(d)
        Rate.objects.update_or_create(
            time_frame=(d, d + timedelta(days=1)),
            smart=True,
            prop=prop,
            defaults={"nightly": price, "label": "Voyajoy Pricing"},
        )

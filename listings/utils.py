from collections import OrderedDict
from datetime import date, timedelta
from urllib.parse import urljoin

from django.conf import settings

from accounts.utils import jwt_generate_token
from cozmo_common.functions import date_range, send_email
from .choices import WeekDays
from .models import Discount

_confirmation_url = urljoin(settings.COZMO_WEB_URL, "confirm-inquiry?key={token}")


def send_inquiry_email(instance):
    token = jwt_generate_token(instance.__class__.__name__, instance.id)
    send_email(
        "listing/email/inquiry.html",
        {
            "book_url": _confirmation_url.format(token=token),
            "inquiry": instance,
            "rates": instance.reservationrate_set.iterator(),
            "fees": instance.reservationfee_set.iterator(),
            "discounts": [
                {"discount_type": Discount.Types(d.discount_type).pretty_name, "amount": d.amount}
                for d in instance.reservationdiscount_set.filter(optional=False).iterator()
            ],
            "payment_schedule": instance.payment_schedule,
            "property": instance.prop,
            "payment_requested": instance.payment_requested,
        },
        "Voyajoy - Reservation Inquiry",
        getattr(instance.guest, "email", None),
    )


def is_weekend(day: date, weekend_days: list = None):
    if weekend_days is None:
        weekend_days = [WeekDays.Sunday.value, WeekDays.Saturday.value]
    return day.weekday() in weekend_days


def split_by_ranges(start: date, days: int, ranges: OrderedDict) -> list:
    result = []
    while days > 0:
        for (field_name, range_days) in ranges.items():
            if days >= range_days:
                end = start + timedelta(days=range_days)
                days = days - range_days
                result.append({"field_name": field_name, "range": (start, end)})
                start = end
                break
    return result


def prepare_prices(rate_groups: tuple, periods: list) -> dict:
    prices = {}
    for period in periods:
        divider = (period["range"][1] - period["range"][0]).days
        for rates in rate_groups:
            for rate in rates:
                if rate is None:
                    continue
                rate_range = date_range(
                    max(period["range"][0], rate["time_frame"].lower or date.min),
                    min(period["range"][1], rate["time_frame"].upper or date.max),
                )
                prices.update(
                    {
                        visit_day: rate[period["field_name"]] / divider
                        if rate[period["field_name"]] > 0
                        else rate["nightly"]
                        for visit_day in rate_range
                    }
                )
                # update days only from nightly period
                if period["field_name"] == "nightly":
                    rate_range = date_range(
                        max(period["range"][0], rate["time_frame"].lower or date.min),
                        min(period["range"][1], rate["time_frame"].upper or date.max),
                    )
                    for visit_day in rate_range:
                        if is_weekend(visit_day):
                            prices[visit_day] = rate["weekend"] or rate["nightly"]
    return prices

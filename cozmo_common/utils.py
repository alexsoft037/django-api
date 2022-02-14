from datetime import datetime

import pytz
from django.utils import timezone


def get_ical_friendly_date(d):
    return d.isoformat().replace("-", "").replace(":", "")


def get_today_dt(tz=None):
    now = timezone.now()
    if tz:
        t = pytz.timezone(tz)
        now = now.astimezone(t)
    return now


def get_today_date(tz=None):
    return get_today_dt(tz).date()


def get_datetime_first_of_this_month(tz=None):
    return datetime.combine(get_today_dt(tz), datetime.min.time())


def format_decimal_to_str(value, digits=2):
    return format(value, f".{digits}f")


def get_dt_from_timestamp(value):
    return datetime.fromtimestamp(int(value))

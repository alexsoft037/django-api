import functools
from datetime import datetime, timedelta
from functools import reduce

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import loader
from django.utils.html import strip_tags


def date_range(start, end):
    for i in range((end - start).days):
        yield start + timedelta(i)


def datetime_to_date(event_date):
    if isinstance(event_date, datetime):
        return event_date.date()
    return event_date


def end_date_plus(start_date, end_date, days=1):
    if start_date != end_date:
        return end_date
    return start_date + timedelta(days=days)


def send_email(template, context, subject, to):
    html_content = loader.get_template(template).render(context)
    send_html_content_email(html_content, subject, to)


def send_html_content_email(html_content, subject, to):
    email = EmailMultiAlternatives(
        subject=subject,
        body=strip_tags(html_content),
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL"),
        to=(to,),
    )
    email.attach_alternative(html_content, "text/html")
    email.send(fail_silentlsettings.ENV=False)


def deep_get(dictionary, *keys):
    return reduce(
        lambda d, key: d.get(key, None) if isinstance(d, dict) else None, keys, dictionary
    )


def non_test_receiver(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if settings.ENV_TYPE == "test":
            return
        value = func(*args, **kwargs)
        return value
    return wrapper

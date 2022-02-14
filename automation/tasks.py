import datetime as dt
import logging
import re
from datetime import timedelta

import pytz
from celery import group
from celery.exceptions import Ignore
from celery.task import periodic_task, task
from django.utils import timezone

from automation.choices import RecipientType
from automation.models import ReservationMessage
from listings.models import Property, Reservation
from message_templates.choices import ReservationEvent
from . import models

logger = logging.getLogger(__name__)


@periodic_task(run_every=dt.timedelta(minutes=15))
def queue_reservation_messages():
    # TODO Prevent sending email multiple times per day on restart
    pks = models.ReservationAutomation.objects.filter(is_active=True).values_list("id", flat=True)
    job = group(queue_reservation_messages_by_schedule.s(pk) for pk in pks)
    job.apply_async()
    return "Scheduled reservation emails"


def get_variable_value(root, keys):
    """
    Grabs the variable (should we try using eval?
    :param root: object with attributes
    :param keys: list of keys that were spllit from a '.' delimited string
    :return:
    """
    print("root: {}/{}".format(root, keys))
    # if not hasattr(root, keys[0]):
    #     return None
    value = getattr(root, keys[0], None) if not isinstance(root, dict) else root.get(keys[0], None)
    if len(keys) == 1:
        return value
    return get_variable_value(value, keys[1:])


def _get_variables(content):
    pattern = re.compile("({{\s*\w+[a-zA-Z._]*\s*}})")
    matches = pattern.findall(content)
    return matches


def _replace_variables(data, content):
    """
    Replaces variables inside template
    :param data:
    :return:
    """
    variables = _get_variables(content)
    formatted_content = content
    for var in variables:
        # validate each variable is legal
        pattern = re.compile("{{\s*(\w+[a-zA-Z._]*)\s*}}")
        matches = pattern.findall(var)
        if matches:
            matched_var = matches[0]
            value = get_variable_value(data, matched_var.split("."))
            if not value:
                continue
            formatted_content = re.sub(var, value, formatted_content)
    return formatted_content


def render_template(reservation, template):
    prop = reservation.prop
    merged_listing = dict()
    merged_listing.update(prop.booking_settings.__dict__)
    merged_listing.update(prop.booking_settings.check_in_out.__dict__)
    merged_listing.update(prop.pricing_settings.__dict__)
    merged_listing.update(prop.availability_settings.__dict__)
    merged_listing.update(prop.descriptions.__dict__)
    data = {
        "reservation": reservation,
        "property": prop,
        "guest": reservation.guest,
        "listing": merged_listing,
        "owner": prop.owner,
    }

    formatted_content = _replace_variables(data, template.content)
    formatted_subject = _replace_variables(data, template.subject)
    formatted_headline = _replace_variables(data, template.headline)
    logger.debug(
        dict(content=formatted_content, subject=formatted_subject, headline=formatted_headline)
    )
    return {
        "subject": formatted_subject,
        "content": f"{formatted_headline}\n\n{formatted_content}",
    }


@task
def queue_reservation_messages_by_schedule(pk):
    """55
     - Fetches schedule object
     - Checks to see if it needs to be executed
        * is_active
        * Reservationmesage exists
        * Check if correct hour by timezone
     - Retrieves and renders template for each reservation
     - Create ReservationMessage -> Sends email
    :param pk:
    :return:
    """
    try:
        res_email = models.ReservationAutomation.objects.get(pk=pk)
        if not res_email.is_active:
            info = "Reservation automation is not active id={}".format(pk)
            logger.info(info)
            return

        logger.info("reservation email={}".format(res_email.__dict__))
        timezone_now = timezone.now()
        today = timezone_now.date()
        day_scheduled = today - timedelta(days=res_email.days_delta)
        time_scheduled = res_email.time

        event_mapping = {
            ReservationEvent.BOOKING: "date_created",  # TODO switch to date_booked instead
            ReservationEvent.CANCELLATION: "date_cancelled",
            ReservationEvent.CHECK_IN: "start_date",
            ReservationEvent.CHECK_OUT: "end_date",
            ReservationEvent.MESSAGE: "date_updated",
            ReservationEvent.CHANGE: "date_updated",  # TODO
        }
        event_key = event_mapping.get(res_email.event)
        logger.info("mapping: {}, {}".format(event_mapping.get(res_email.event), day_scheduled))
        reservations = list()

        reservation_ids_with_existing_messages = (
            ReservationMessage.objects.filter(
                schedule=res_email,
            )
            .values_list("reservation_id", flat=True)
            .distinct()
        )

        logger.info("exclude reservation ids = {}".format(reservation_ids_with_existing_messages))

        timezones = (
            Property.objects.exclude(time_zone__isnull=True)
            .exclude(time_zone__exact="")
            .values_list("time_zone", flat=True)
            .distinct()
        )
        logger.info("timzones={}".format(timezones))
        for tz in timezones:
            t = pytz.timezone(tz)
            now = timezone.now()
            tz_now_days_delta = now.astimezone(t) - timedelta(days=res_email.days_delta)

            is_scheduled_hour = tz_now_days_delta.hour == time_scheduled.hour
            if not is_scheduled_hour:
                continue

            data = {
                "prop__organization": res_email.organization,
                "prop__time_zone": tz,
                "prop__pk": res_email.template.prop_id,
                event_key: tz_now_days_delta.date(),
                "status": Reservation.Statuses.Accepted.value
            }

            logger.info("data={}".format(data))

            reservations.extend(
                Reservation.objects.filter(**data).exclude(
                    pk__in=reservation_ids_with_existing_messages
                )
            )

        logger.info("reservations: {}".format(reservations))
        for reservation in reservations:
            rendered_content = render_template(
                reservation=reservation, template=res_email.template
            )
            logger.info("reservation={}".format(reservation))
            if res_email.recipient_type == RecipientType.guest.value:
                recipient = reservation.guest.email
            elif res_email.recipient_type == RecipientType.email.value:
                recipient = res_email.recipient_address
            else:
                continue

            recipient_info = {"cc": res_email.cc_address, "bcc": res_email.bcc_address}
            ReservationMessage.objects.create(
                event=res_email.event,
                reservation=reservation,
                organization=res_email.organization,
                schedule=res_email,
                recipient=recipient,
                recipient_info=recipient_info,
                **rendered_content,
            )
        return "Completed queue_reservation_email - id={}, count={}".format(pk, len(reservations))
    except models.ReservationAutomation.DoesNotExist:
        info = "ReservationEmail id={} does not exist".format(pk)
        logger.info(info)
        raise Ignore(info)

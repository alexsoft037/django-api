from datetime import timedelta

from django.db import models
from django.template import loader
from django.utils import timezone

from accounts.choices import ApplicationTypes
from accounts.models import Organization
from notifications.models import Notification


# from celery.task import periodic_task  # Disabled for COZ-2061


# @periodic_task(run_every=timedelta(days=1))  # Disabled for COZ-2061
def notify_trial_organisations():
    today = timezone.now().date()
    start_date = today - timedelta(days=4)
    half_date = today - timedelta(days=7)
    expiring_date = today - timedelta(days=12)
    emails_by_date = {
        start_date: "account/email/email_trial_start.html",
        half_date: "account/email/email_trial_half.html",
        expiring_date: "account/email/email_trial_end.html",
    }
    date_q_objects = models.Q()
    for date in emails_by_date.keys():
        date_q_objects.add(models.Q(date_created__contains=date), models.Q.OR)

    organizations = Organization.objects.filter(
        date_q_objects, applications__contains=[ApplicationTypes.iCal_Magic.value]
    )

    Notification.objects.bulk_create(
        Notification(
            channel=Notification.Channels.Email.value,
            content=loader.get_template(emails_by_date[organization.date_created.date()]).render(
                {"user": organization.owner}
            ),
            to=organization.owner,
            content_object=organization,
        )
        for organization in organizations
    )

    return "Preparation of notifications of iCall Magic trial period"

from django.db import models

from .choices import PaymentSchedule, PaymentTemplate


class PaymentSetting(models.Model):

    payment_schedule = models.SmallIntegerField(
        choices=PaymentSchedule.choices(), default=None, null=True, blank=True
    )
    payment_template = models.SmallIntegerField(
        choices=PaymentTemplate.choices(), default=None, null=True, blank=True
    )
    payment_custom_date = models.DateTimeField(default=None, null=True, blank=True)

    class Meta:
        abstract = True

from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import JSONField
from django.db import models

from automation.choices import RecipientType
from cozmo_common.db.models import TimestampModel
from message_templates.choices import ReservationEvent, TransportMethod


class BaseAutomation(TimestampModel):

    is_active = models.BooleanField(default=True)
    organization = models.ForeignKey(
        "accounts.Organization", related_name="+", on_delete=models.CASCADE
    )

    class Meta:
        abstract = True

    @classmethod
    def get_subclasses(cls, exclude_self=True):
        content_types = ContentType.objects.filter(app_label=cls._meta.app_label)
        if exclude_self:
            content_types = content_types.exclude(model=cls._meta.model_name)

        return [
            model
            for model in (ct.model_class() for ct in content_types)
            if model is not None and issubclass(model, cls)
        ]

    def apply(self):
        raise NotImplementedError()


class ReservationAutomation(BaseAutomation):

    days_delta = models.SmallIntegerField()
    event = models.PositiveSmallIntegerField(choices=ReservationEvent.choices())
    time = models.TimeField()
    method = models.PositiveSmallIntegerField(
        choices=TransportMethod.choices(), default=TransportMethod.AUTO
    )
    recipient_type = models.PositiveSmallIntegerField(
        choices=RecipientType.choices(), default=RecipientType.guest
    )
    recipient_address = models.CharField(max_length=128, blank=True, null=True, default="")
    cc_address = JSONField(default=list())
    bcc_address = JSONField(default=list())
    template = models.ForeignKey(
        "message_templates.Template",
        related_name="schedule_set",
        on_delete=models.CASCADE,
        null=True,
    )

    class Meta:
        permissions = (("view_reservationautomation", "Can view reservation automations"),)


class ReservationMessage(TimestampModel):

    event = models.PositiveSmallIntegerField(choices=ReservationEvent.choices())
    reservation = models.ForeignKey(
        "listings.Reservation",
        related_name="reservation_emails",
        on_delete=models.CASCADE,
        null=True,
    )
    organization = models.ForeignKey(
        "accounts.Organization", related_name="+", on_delete=models.CASCADE
    )
    schedule = models.ForeignKey(
        ReservationAutomation, related_name="+", on_delete=models.SET_NULL, null=True
    )
    message = models.ForeignKey(
        "send_mail.Message", related_name="+", on_delete=models.SET_NULL, null=True
    )
    content = models.TextField(blank=True, default="")
    subject = models.TextField(null=True, blank=True, default="")
    recipient = models.CharField(max_length=128, default="")
    recipient_info = JSONField(default={})

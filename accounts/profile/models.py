from django.contrib.auth import get_user_model
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from accounts.models import Organization
from listings.choices import CancellationPolicy
from .choices import Plan
from .models_base import PaymentSetting as PaymentSettingBase

User = get_user_model()


def choose_plan(team, properties):
    """Return correct plan based on input data."""
    return Plan.SINGLE.value  # FIXME


class PlanSettings(models.Model):

    team = models.IntegerField()
    properties = models.IntegerField()
    cancellation_policy = models.CharField(
        max_length=2,
        choices=CancellationPolicy.choices(),
        default=CancellationPolicy.Unknown.value,
        blank=True,
    )
    month_days = models.PositiveSmallIntegerField(
        default=30, validators=[MinValueValidator(28), MaxValueValidator(31)]
    )
    trip_advisor_sync = models.BooleanField(default=False)
    booking_sync = models.BooleanField(default=False)
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE)

    @property
    def plan(self):
        return choose_plan(self.team, self.properties)


class PaymentSettings(PaymentSettingBase):

    organization = models.OneToOneField(Organization, on_delete=models.CASCADE)

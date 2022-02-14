from functools import partial

from django.contrib.auth import get_user_model
from django.db import models

from chat.choices import ChatSetting
from cozmo_common.db.models import TimestampModel

User = get_user_model()


class Settings(TimestampModel):

    SettingsField = partial(
        models.PositiveIntegerField, choices=ChatSetting.choices(), default=ChatSetting.DISABLED
    )

    org_settings = models.OneToOneField(
        "settings.OrganizationSettings",
        related_name="chat_settings",
        on_delete=models.CASCADE,
        null=True,
    )
    enabled = models.BooleanField(default=False)
    early_bag_dropoff_enabled = SettingsField()
    discount_enabled = SettingsField()
    refund_enabled = SettingsField()
    early_check_in_enabled = SettingsField()
    thanks_enabled = SettingsField()
    distance_enabled = SettingsField()
    recommendations_enabled = SettingsField()
    amenities_enabled = SettingsField()
    wifi_enabled = SettingsField()
    availability_enabled = SettingsField()
    late_check_out_enabled = SettingsField()
    location_enabled = SettingsField()
    cancellation_enabled = SettingsField()
    pets_enabled = SettingsField()

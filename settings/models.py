import logging

from django.db import models

from accounts.models import Organization
from cozmo_common.db.models import TimestampModel

logger = logging.getLogger(__name__)


class OrganizationSettings(TimestampModel):
    """Org settings"""

    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name="settings"
    )

    channel_network_enabled = models.BooleanField(default=False)

    class Meta:
        permissions = (("view_organizationsettings", "Can view organization settings"),)

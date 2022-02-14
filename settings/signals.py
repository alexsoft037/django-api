import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import Organization
from .models import OrganizationSettings

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Organization)
def create_organization_settings(sender, instance, created, **kwargs):
    # TODO write test cases
    if created:
        OrganizationSettings.objects.create(organization=instance)

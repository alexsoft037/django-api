import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from chat.models import Settings
from settings.models import OrganizationSettings

logger = logging.getLogger(__name__)


@receiver(post_save, sender=OrganizationSettings)
def create_chat_settings(sender, instance, created, **kwargs):
    # TODO write test cases
    if created:
        Settings.objects.create(org_settings=instance)

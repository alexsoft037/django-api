from django.db.models.signals import post_save
from django.dispatch import receiver

from rental_integrations.models import BaseAccount, IntegrationSetting


@receiver(post_save)
def create_integration_setting(sender, instance, **kwargs):
    if issubclass(sender, BaseAccount):
        created = kwargs["created"]
        if created:
            IntegrationSetting.objects.get_or_create(
                organization=instance.organization,
                channel_type=instance.channel_type,
                defaults={"sync": True},
            )

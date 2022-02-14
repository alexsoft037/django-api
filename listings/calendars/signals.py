from django.db.models.signals import post_save
from django.dispatch import receiver

from listings.models import Property
from .models import CozmoCalendar


@receiver(post_save, sender=Property)
def create_calendar(sender, **kwargs):
    created = kwargs["created"]
    if created:
        instance = kwargs["instance"]
        CozmoCalendar.objects.create(prop=instance)

from django.db.models.signals import post_delete, post_save
from django.dispatch import Signal, receiver
from guardian.shortcuts import assign_perm, remove_perm

from .models import AdditionalFee, Image, Property, Rate, Reservation, SchedulingAssistant, \
    GroupUserAssignment


@receiver(post_delete, sender=Image)
def image_remove_from_storage(sender, **kwargs):
    instance = kwargs["instance"]
    instance.url.storage.delete(instance.url.name)


def schedule_sync(instance):
    pass
    # if instance.is_trip_advisor_sync_enabled:
    #     update_or_create_listings.s([instance.id]).apply_async()


@receiver(post_save, sender=Property)
def create_scheduling_assistant(sender, instance, **kwargs):
    created = kwargs["created"]
    if created:
        SchedulingAssistant.objects.create(prop=instance)
    schedule_sync(instance)


@receiver(post_save, sender=Rate)
def after_rate_save(sender, instance, **kwargs):
    schedule_sync(instance.prop)


@receiver(post_save, sender=AdditionalFee)
def after_fee_save(sender, instance, **kwargs):
    schedule_sync(instance.prop)


@receiver(post_save, sender=Reservation)
def after_reservation_save(sender, instance, **kwargs):
    schedule_sync(instance.prop)


property_changed = Signal(providing_args=["instance"])
reservation_changed = Signal(providing_args=["changes", "instance"])


@receiver(post_save, sender=GroupUserAssignment)
def assign_group_permissions(sender, instance, created, **kwargs):
    if created:
        assign_perm("group_access", instance.user, instance.group)


@receiver(post_delete, sender=GroupUserAssignment)
def remove_group_permissions(sender, instance, **kwargs):
    remove_perm("group_access", instance.user, instance.group)

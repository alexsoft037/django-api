from contextlib import suppress

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from listings.models import AvailabilitySettings, Blocking, PricingSettings, Property, Reservation
from listings.signals import property_changed
from rental_integrations.airbnb.models import AirbnbSync, Listing
from rental_integrations.choices import ListingApprovalStatus, ListingStatus
from .service import AirbnbService
from .tasks import sync_availability, sync_calendar, sync_pricing


@receiver(property_changed, sender=Property)
def push_to_airbnb(sender, instance: Property, **kwargs):
    pass
    # app = instance.airbnb_sync
    # if app is None:
    #     return
    #
    # service = AirbnbService(app.user_id, app.access_token)
    # listing = service.to_airbnb(instance)
    # service.update_listing(listing)


@receiver(post_save, sender=Listing)
def set_airbnb_listing_live(sender, **kwargs):
    created = kwargs["created"]
    if not created:
        instance = kwargs["instance"]
        app = instance.owner
        if app is None:
            #  TODO this should be logged
            return
        #  TODO check if user allows publishing automatically
        service = AirbnbService(app.user_id, app.access_token)
        service.push_listing_status(instance.external_id, active=True)


@receiver(post_save, sender=AirbnbSync)
def publish_airbnb_listing(sender, **kwargs):
    created = kwargs["created"]
    if not created:
        instance = kwargs["instance"]
        service = instance.account.service
        is_new_listing = instance.status == ListingStatus.init
        is_ready = instance.approval_status == ListingApprovalStatus.approved
        auto_push_enabled = instance.auto_push_enabled
        is_ready_to_publish = is_new_listing and is_ready and auto_push_enabled

        if is_ready_to_publish:
            # TODO move this to background task with celery
            result = service.push_listing_status(listing_id=instance.external_id, active=True)
            if "has_availability" in result:
                instance.status = (
                    ListingStatus.listed
                    if result["has_availability"]
                    else ListingStatus.failed_publish
                )
                instance.save()


@receiver(post_save, sender=AvailabilitySettings)
def update_availability_settings(sender, **kwargs):
    created = kwargs["created"]
    if not created:
        instance = kwargs["instance"]

        with suppress(AirbnbSync.DoesNotExist):
            airbnb_sync = instance.prop.airbnb_sync.get()
            sync_availability.delay(airbnb_sync.id)


@receiver(post_save, sender=PricingSettings)
def update_pricing_settings(sender, **kwargs):
    created = kwargs["created"]
    if not created:
        instance = kwargs["instance"]

        with suppress(AirbnbSync.DoesNotExist):
            airbnb_sync = instance.prop.airbnb_sync.get()
            sync_pricing.delay(airbnb_sync.id)


@receiver(post_save, sender=Blocking)
def update_calendar_blocking(sender, **kwargs):
    instance = kwargs["instance"]

    with suppress(AirbnbSync.DoesNotExist):
        airbnb_sync = instance.prop.airbnb_sync.get()
        sync_calendar.delay(airbnb_sync.id)


@receiver(post_delete, sender=Blocking)
def delete_calendar_blocking(sender, **kwargs):
    instance = kwargs["instance"]

    with suppress(AirbnbSync.DoesNotExist):
        airbnb_sync = instance.prop.airbnb_sync.get()
        sync_calendar.delay(airbnb_sync.id)


@receiver(post_save, sender=Reservation)
def update_reservation_calendar(sender, **kwargs):
    instance = kwargs["instance"]

    with suppress(AirbnbSync.DoesNotExist):
        if hasattr(instance.prop, "airbnb_sync"):
            airbnb_sync = instance.prop.airbnb_sync.get()
            sync_calendar.delay(airbnb_sync.id)

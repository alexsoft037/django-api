import datetime as dt
from functools import reduce
from logging import getLogger

from celery import group
from celery.exceptions import Ignore
from celery.task import periodic_task, task

from rental_integrations.airbnb.serializers import AirbnbListingSerializer
from .models import AirbnbSync

logger = getLogger(__name__)


@periodic_task(run_every=dt.timedelta(hours=3))
def queue_sync_calendar_availability():
    pks = AirbnbSync.objects.filter(sync_enabled=True).values_list("id", flat=True)
    job = group(sync_calendar.s(pk) for pk in pks)
    job.apply_async()
    return "Scheduled sync calendar"


@periodic_task(run_every=dt.timedelta(hours=6))
def queue_sync_rates_and_availability():
    pks = AirbnbSync.objects.filter(sync_enabled=True).values_list("id", flat=True)
    pricing_jobs = [sync_pricing.s(pk) for pk in pks]
    availability_jobs = [sync_availability.s(pk) for pk in pks]
    job = group(pricing_jobs + availability_jobs)
    job.apply_async()
    return "Scheduled sync rates and availability"


# @periodic_task(run_every=dt.timedelta(hours=2))
def queue_sync_listing_extras():
    pks = AirbnbSync.objects.filter(sync_enabled=True).values_list("id", flat=True)
    tasks = (sync_descriptions, sync_booking_settings, sync_photos, sync_rooms)
    jobs = group(reduce(lambda x, y: x + y, [[t.s(pk) for pk in pks] for t in tasks]))
    jobs.apply_async()
    return "Scheduled sync listing extras"


@task
def sync_calendar(pk):
    try:
        sync = AirbnbSync.objects.get(pk=pk)
        if not sync.sync_enabled:
            info = f"Sync is not enabled for this Airbnb listing={sync.external_id}. Skipping.."
            logger.info(info)
            return

        serializer = AirbnbListingSerializer(instance=sync.prop)
        calendar = serializer._calendar_operations()
        if calendar:
            service = sync.account.service
            service.push_availability(sync.external_id, calendar)
        return f"Completed {sync_calendar.__name__} - id={pk}"
    except AirbnbSync.DoesNotExist:
        info = f"AirbnbSync id={pk} does not exist"
        logger.info(info)
        raise Ignore(info)


@task
def sync_pricing(pk):
    try:
        sync = AirbnbSync.objects.get(pk=pk)
        if not sync.sync_enabled:
            info = f"Sync is not enabled for this Airbnb listing={sync.external_id}. Skipping.."
            logger.info(info)
            return

        serializer = AirbnbListingSerializer(instance=sync.prop)
        pricing_settings = serializer._pricing_settings()
        service = sync.account.service
        service.push_pricing_settings(sync.external_id, pricing_settings)
        return f"Completed {sync_pricing.__name__} - id={pk}"
    except AirbnbSync.DoesNotExist:
        info = f"AirbnbSync id={pk} does not exist"
        logger.info(info)
        raise Ignore(info)


@task
def sync_availability(pk):
    try:
        sync = AirbnbSync.objects.get(pk=pk)
        if not sync.sync_enabled:
            info = f"Sync is not enabled for this Airbnb listing={sync.external_id}. Skipping.."
            logger.info(info)
            return

        serializer = AirbnbListingSerializer(instance=sync.prop)
        availability_rules = serializer._availability_rules()
        service = sync.account.service
        service.push_availability_rule(sync.external_id, availability_rules)
        return f"Completed {sync_availability.__name__} - id={pk}"
    except AirbnbSync.DoesNotExist:
        info = f"AirbnbSync id={pk} does not exist"
        logger.info(info)
        raise Ignore(info)


@task
def sync_descriptions(pk):
    try:
        sync = AirbnbSync.objects.get(pk=pk)
        if not sync.sync_enabled:
            info = f"Sync is not enabled for this Airbnb listing={sync.external_id}. Skipping.."
            logger.info(info)
            return

        serializer = AirbnbListingSerializer(instance=sync.prop)
        descriptions = serializer._listing_descriptions()
        service = sync.account.service
        service.push_descriptions(sync.external_id, descriptions)
        return f"Completed {sync_descriptions.__name__} - id={pk}"
    except AirbnbSync.DoesNotExist:
        info = f"AirbnbSync id={pk} does not exist"
        logger.info(info)
        raise Ignore(info)


@task
def sync_booking_settings(pk):
    try:
        sync = AirbnbSync.objects.get(pk=pk)
        if not sync.sync_enabled:
            info = f"Sync is not enabled for this Airbnb listing={sync.external_id}. Skipping.."
            logger.info(info)
            return

        serializer = AirbnbListingSerializer(instance=sync.prop)
        booking_settings = serializer._booking_settings()
        service = sync.account.service
        service.push_booking_settings(sync.external_id, booking_settings)
        return f"Completed {sync_booking_settings.__name__} - id={pk}"
    except AirbnbSync.DoesNotExist:
        info = f"AirbnbSync id={pk} does not exist"
        logger.info(info)
        raise Ignore(info)


@task
def sync_photos(pk):
    try:
        sync = AirbnbSync.objects.get(pk=pk)
        if not sync.sync_enabled:
            info = f"Sync is not enabled for this Airbnb listing={sync.external_id}. Skipping.."
            logger.info(info)
            return

        serializer = AirbnbListingSerializer(instance=sync.prop)
        photos = serializer._listing_photos()
        service = sync.account.service
        service.push_photos(sync.external_id, photos)
        return f"Completed {sync_photos.__name__} - id={pk}"
    except AirbnbSync.DoesNotExist:
        info = f"AirbnbSync id={pk} does not exist"
        logger.info(info)
        raise Ignore(info)


@task
def sync_rooms(pk):
    try:
        sync = AirbnbSync.objects.get(pk=pk)
        if not sync.sync_enabled:
            info = f"Sync is not enabled for this Airbnb listing={sync.external_id}. Skipping.."
            logger.info(info)
            return

        serializer = AirbnbListingSerializer(instance=sync.prop)
        rooms = serializer._listing_rooms()
        service = sync.account.service
        service.push_listing_rooms(sync.external_id, rooms)
        return f"Completed {sync_rooms.__name__} - id={pk}"
    except AirbnbSync.DoesNotExist:
        info = f"AirbnbSync id={pk} does not exist"
        logger.info(info)
        raise Ignore(info)


@periodic_task(run_every=dt.timedelta(hours=2))
def airbnb_push():
    # for app in AirbnbApp.objects.all().only("user_id", "access_token"):
    #     service = AirbnbService(app.user_id, app.access_token)
    #     service.push_listings(map(
    #         service.to_airbnb,
    #         app.property_set(manager='objects').with_coordinates()
    #     ))
    return "Finished scheduled push to Airbnb"


@task
def airbnb_push_initial(app_id):
    # app = AirbnbApp.objects.get(id=app_id)
    # properties = app.property_set.all()
    # service = AirbnbService(app.user_id, app.access_token)
    #
    # listings_data = service.push_listings(map(service.to_airbnb, properties))
    #
    # for prop, listing in zip(properties, listings_data):
    #     if "id" not in listing:
    #         logger.warning("No id in Airbnb listing: %s", listing)
    #         continue
    #
    #     prop.airbnb_listing.external_id = listing["id"]
    #     prop.airbnb_listing.save()
    #
    #     Photo.objects.bulk_create(
    #         Photo(external_id=photo["photo_id"], image_id=image.id)
    #         for image, photo in zip(prop.image_set.only("id"), listing.get("photos", []))
    #         if "photo_id" in photo and not hasattr(image, "airbnb_photo")
    #     )

    return f"Initial Airbnb push to {app_id}"

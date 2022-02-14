from logging import getLogger

logger = getLogger(__name__)


# @periodic_task(run_every=dt.timedelta(hours=2))
# def airbnb_push():
#     for app in AirbnbApp.objects.all().only("user_id", "access_token"):
#         service = AirbnbService(app.user_id, app.access_token)
#         service.push_listings(map(
#             service.to_airbnb,
#             app.property_set(manager='objects').with_coordinates()
#         ))
#     return "Finished scheduled push to Airbnb"
#
#
# @task
# def airbnb_push_initial(app_id):
#     app = AirbnbApp.objects.get(id=app_id)
#     properties = app.property_set.all()
#     service = AirbnbService(app.user_id, app.access_token)
#
#     listings_data = service.push_listings(map(service.to_airbnb, properties))
#
#     for prop, listing in zip(properties, listings_data):
#         if "id" not in listing:
#             logger.warning("No id in Airbnb listing: %s", listing)
#             continue
#
#         prop.airbnb_listing.external_id = listing["id"]
#         prop.airbnb_listing.save()
#
#         Photo.objects.bulk_create(
#             Photo(external_id=photo["photo_id"], image_id=image.id)
#             for image, photo in zip(prop.image_set.only("id"), listing.get("photos", []))
#             if "photo_id" in photo and not hasattr(image, "airbnb_photo")
#         )
#
#     return f"Initial Airbnb push to {app_id}"

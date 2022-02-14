import logging

import googlemaps
from django.conf import settings

from services.errors import ServiceError

logger = logging.getLogger(__name__)


class GoogleService:
    def __init__(self):
        self.client = googlemaps.Client(key=settings.GOOGLE_API_KEY)

    def get_timezone(self, latitude, longitude):
        assert latitude and longitude, "latitude and longitude is required"
        location = (latitude, longitude)
        result = self.client.timezone(location)
        if result["status"] == "OK":
            return result["timeZoneId"]
        raise ServiceError("Unable to find result")

    def get_distance_by_address(self, origin, destination, units="imperial"):
        result = self.client.distance_matrix(
            units=units, origins=[origin], destinations=[destination]
        )

        if result["status"] == "OK":
            return dict(
                destination=result["destination_addresses"][0],
                origin=result["origin_addresses"][0],
                driving_distance=result["rows"][0]["elements"][0]["distance"]["text"],
                driving_time=result["rows"][0]["elements"][0]["duration"]["text"],
            )
        raise ServiceError("Unable to find result")

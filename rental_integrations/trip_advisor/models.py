import logging

from django.db import models
from django.http.request import HttpRequest

from cozmo_common.enums import IntChoicesEnum
from listings.models import Property
from listings.serializers import PropertyCreateSerializer
from rental_integrations.models import BaseAccount, BaseListing, ChannelSync
from .service import TripAdvisorClient, TripParser
from .service_serializers import camelize

logger = logging.getLogger(__name__)


class TripAdvisorStatus(IntChoicesEnum):
    pending = 0
    installed = 1


class TripAdvisorAccount(BaseAccount):
    """Representation of a connected tripadvisor.com account."""

    status = models.PositiveIntegerField(
        choices=TripAdvisorStatus.choices(), default=TripAdvisorStatus.pending, blank=True
    )

    @property
    def channel_type(self) -> str:
        return "TripAdvisor"

    @property
    def service(self):
        if not hasattr(self, "_service"):
            self._service = TripAdvisorClient(self.user_id)
        return self._service

    def update_listings(self, secret=None) -> bool:
        client = self.service
        status_code, listings_data = client.get_listings()

        if status_code >= 300:
            return False

        self.listing_set.all().delete()
        Listing.objects.bulk_create(
            Listing(owner=self, data=camelize(data)) for data in listings_data
        )
        return True

    def update_reservations(self, secret=None) -> bool:
        ...  # TODO

    def _import_listings(self):
        client = self.service
        listings = client.get_listings()
        self.listings_set.all().delete()
        Listing.objects.bulk_create(Listing(owner=self, data=camelize(data)) for data in listings)

    def import_listings(self, ids=None):
        listings = self.listing_set.all()
        if ids is not None:
            listings = listings.filter(id__in=ids)

        for listing in listings.all():
            if Property.objects.filter(user=self.user, external_id=listing.external_id).exists():
                logger.info("Listing %s: cannot import as it already exists", listing.id)
                continue

            request = HttpRequest()
            request.user = self.user
            serializer = PropertyCreateSerializer(
                data=listing._to_cozmo(), context={"request": request}
            )
            if serializer.is_valid():
                serializer.save(external_id=listing.external_id)
            else:
                logger.warning("Listing %s: invalid listings.Property data", listing.id)

        # self.import_reservations()


class Listing(BaseListing):
    """Representation of a listing imported from tripadvisor.com."""

    owner = models.ForeignKey(TripAdvisorAccount, on_delete=models.CASCADE)
    parser = TripParser

    @property
    def external_id(self) -> str:
        return self.data.get("externalListingReference", "")

    @property
    def name(self) -> str:
        return self.data.get("descriptions", {}).get("listingTitle", "")

    @property
    def image(self) -> str:
        return self.data.get("photos", [{}])[0].get("url", "")

    @property
    def address(self) -> str:
        return self.data.get("address", {}).get("address", "")

    @property
    def active(self) -> bool:
        return self.data.get("active", False)

    @property
    def url(self) -> str:
        return self.data.get("url", "")

    def _to_cozmo(self) -> dict:
        return self.parser.to_cozmo(self.data)

    def _from_cozmo(self, cozmo_property: Property, commit=False):
        self.data = self.parser.from_cozmo(cozmo_property)

        if commit:
            self.save()


class TripAdvisorSync(ChannelSync):

    account = models.ForeignKey(TripAdvisorAccount, on_delete=models.CASCADE, null=True)
    prop = models.ForeignKey(
        Property, on_delete=models.CASCADE, related_name="tripadvisor_sync", null=True
    )
    name = "TripAdvisor"

    def get_info(self):
        return {"name": "tripadvisor", "type": self.channel_type, "status": "listed", "id": 0}

from logging import getLogger
from operator import itemgetter

from django.conf import settings
from django.db import models
from django.utils import timezone

from crm.models import Contact
from listings.models import PricingSettings, Property, Reservation
from rental_integrations.models import BaseAccount, BaseListing
from .service import BookingXmlClient

logger = getLogger(__name__)


def merge_dict(to_dict, from_dict):
    for k, from_value in from_dict.items():
        if k in to_dict and isinstance(from_value, dict) and isinstance(to_dict[k], dict):
            merge_dict(to_dict[k], from_value)
        else:
            to_dict[k] = from_value


class BookingAccount(BaseAccount):
    """Representation of a connected booking.com account."""

    @property
    def service(self):
        if not hasattr(self, "_service"):
            self._service = BookingXmlClient(
                user=self.user_id, secret=settings.BOOKING_CLIENT_SECRET
            )
        return self._service

    @property
    def channel_type(self) -> str:
        return "Booking"

    def update_listings(self, secret=None) -> bool:
        status_code, listings_data = self.service.get_listings()

        if status_code >= 300:
            return False

        self.listing_set.all().delete()  # FIXME This removes possibly not imported reservations
        Listing.objects.bulk_create(Listing(owner=self, data=data) for data in listings_data)
        return True

    def import_listings(self, ids=None) -> bool:
        listings = self.listing_set.all()
        if ids is not None:
            listings = listings.filter(id__in=ids)

        for data in listings.values_list("data", flat=True):
            prop, created = Property.objects.update_or_create(
                organization=self.organization,
                external_id=f"{self.channel_type}:{data['id']}",
                defaults={
                    "name": data["name"],
                    "date_updated": timezone.now(),
                    "status": Property.Statuses.Active.value,
                    "max_guests": max(map(itemgetter("max_persons"), data["rates"])),  # FIXME
                },
            )
            BookingSync.objects.update_or_create(
                prop=prop, organization=self.organization, defaults={"external_id": data["id"]}
            )
            pricing_settings_data = {
                "included_guests": min(map(itemgetter("max_persons"), data["rates"]))  # FIXME
            }
            if created:
                prop.pricing_settings = PricingSettings.objects.create(
                    nightly=0, **pricing_settings_data
                )
            else:
                for attr, value in pricing_settings_data.items():
                    setattr(prop.pricing_settings, attr, value)
                prop.pricing_settings.save()
            prop.save()
        self.import_reservations()

        return True

    def import_reservations(self):
        for listing in self.listing_set.filter(data__has_key="reservations"):
            try:
                prop = self.organization.property_set.get(
                    external_id=f"{self.channel_type}:{listing.external_id}"
                )
                reservations = listing.data["reservations"]
            except Property.DoesNotExist:
                reservations = []

            for reservation in reservations:
                if reservation["status"] == "cancelled":
                    prop.reservation_set.filter(
                        external_id=reservation["roomreservation_id"]
                    ).delete()
                else:
                    contact, _ = Contact.objects.get_or_create(
                        organization=prop.organization, defaults=reservation["customer"]
                    )

                    res, _ = prop.reservation_set.update_or_create(
                        external_id=reservation["roomreservation_id"],
                        defaults={
                            "start_date": reservation["arrival_date"],
                            "end_date": reservation["departure_date"],
                            "price": reservation["totalprice"],
                            "paid": "0.00",
                            "guests_adults": reservation["numberofguests"],
                            "prop": prop,
                            "guest": contact,
                            "source": Reservation.Sources.Booking.value,
                        },
                    )

            del listing.data["reservations"]
            listing.save()

    def update_reservations(self, secret=None):
        status, reservations = self.service.get_reservations()

        for reservation in reservations:
            raw_customer = reservation["customer"]
            reservation_data = {
                "customer": {
                    "avatar": "",
                    "first_name": raw_customer["first_name"],
                    "last_name": raw_customer["last_name"],
                    "email": raw_customer["email"],
                    "phone": raw_customer["telephone"],
                },
                "hotel_id": reservation["hotel_id"],
                "status": reservation["status"],
            }
            for room in reservation["room"]:
                room.update(reservation_data)
                room_id = room["id"]
                listing, new = self.listing_set.get_or_create(
                    data__id=room_id,
                    data__hotel_id=room["hotel_id"],
                    defaults={
                        "owner": self,
                        "data": {
                            "id": room_id,
                            "hotel_id": room["hotel_id"],
                            "_raw_reservations": [reservation],
                        },
                    },
                )
                if new:
                    logger.warning("Updating reservation(s) for unknown listing id=%s", room_id)
                else:
                    listing.data.setdefault("_raw_reservations", []).append(reservation)

                listing._save_reservation(room)
                listing.save()


class Listing(BaseListing):
    """Representation of a listing imported from booking.com."""

    owner = models.ForeignKey(BookingAccount, on_delete=models.CASCADE)

    @property
    def external_id(self) -> str:
        return self.data["id"]

    @property
    def name(self) -> str:
        return self.data["name"]

    @property
    def image(self) -> str:
        return ""

    @property
    def address(self) -> str:
        return ""

    def _save_reservation(self, reservation: dict):
        listing_reservations = self.data.setdefault("reservations", [])

        status = reservation["status"]

        if status in "new":
            listing_reservations.append(reservation)
        elif status in ("modified", "cancelled"):
            for index, res in enumerate(listing_reservations):
                if reservation["id"] == res["id"]:
                    merge_dict(listing_reservations[index], reservation)
                    break
            else:
                listing_reservations.append(reservation)


class BookingSync(models.Model):

    prop = models.OneToOneField(Property, on_delete=models.CASCADE, related_name="booking")
    external_id = models.CharField(max_length=255, default="")
    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE)
    sync_enabled = models.BooleanField(default=True)

    last_sync = models.DateTimeField(null=True, blank=True)
    date_updated = models.DateTimeField(auto_now=True, null=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)

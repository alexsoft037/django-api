from django.contrib.postgres.fields import JSONField
from django.db import models

from cozmo_common.db.models import TimestampModel
from listings.models import Property
from rental_integrations.airbnb.choices import CancellationPolicy, ReservationStatus
from rental_integrations.airbnb.constants import LISTING_URL_TEMPLATE
from rental_integrations.airbnb.service import AirbnbService
from rental_integrations.models import BaseAccount, BaseListing, ChannelSync


class AirbnbAccount(BaseAccount):

    access_token = models.TextField()
    refresh_token = models.TextField()
    email = models.EmailField(null=True, default="")
    image_url = models.URLField(null=True, default="")
    image_url_large = models.URLField(null=True, default="")
    first_name = models.CharField(max_length=64, null=True, default="")
    last_name = models.CharField(max_length=64, null=True, default="")

    @property
    def service(self):
        if not hasattr(self, "_service"):
            self._service = AirbnbService(user=self.user_id, secret=self.access_token)
        return self._service

    @property
    def channel_type(self) -> str:
        return "Airbnb"


class Listing(BaseListing):
    owner = models.ForeignKey(AirbnbAccount, on_delete=models.CASCADE, null=True)

    @property
    def external_id(self) -> str:
        return self.data["id"]


class Photo(models.Model):

    external_id = models.CharField(max_length=100)
    image = models.OneToOneField(
        "listings.Image", on_delete=models.CASCADE, related_name="airbnb_photo"
    )


class User(TimestampModel):

    email = models.EmailField(null=True, blank=True, default="")
    first_name = models.CharField(max_length=64, blank=True, default="")
    last_name = models.CharField(max_length=64, blank=True, default="")
    user_id = models.IntegerField(null=True, default=None)
    managed_business_entity_id = models.IntegerField(null=True, default=None)
    phone = models.CharField(max_length=32, default="")
    picture_url = models.URLField(null=True, blank=True, default="")
    picture_url_large = models.URLField(null=True, blank=True, default="")
    airbnb_app = models.OneToOneField(
        "app_marketplace.AirbnbApp", on_delete=models.CASCADE, related_name="airbnb_user"
    )


class Guest(TimestampModel):

    first_name = models.CharField(max_length=64, blank=True, default="")
    last_name = models.CharField(max_length=64, blank=True, default="")
    guest_id = models.IntegerField(null=True, default=None)
    preferred_locale = models.CharField(max_length=4, blank=True, default="")
    phone_numbers = JSONField(default=[])


class Reservation(TimestampModel):

    reservation = models.OneToOneField(
        "listings.Reservation",
        on_delete=models.CASCADE,
        related_name="external_reservation",
        null=True,
        blank=True,
        default=None,
    )
    confirmation_code = models.CharField(max_length=255, blank=False, unique=True)

    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    number_of_guests = models.IntegerField(null=True, default=None)
    guest_id = models.IntegerField(null=True, default=None)
    guest_email = models.EmailField(null=True, blank=True, default="")
    guest_first_name = models.CharField(max_length=64, blank=True, default="")
    guest_last_name = models.CharField(max_length=64, blank=True, default="")
    guest_preferred_locale = models.CharField(max_length=4, blank=True, default="")
    guest_phone_numbers = JSONField(default=[])
    booked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    # Replaced expected_payout_amount, listing_host_fee
    expected_payout_amount_accurate = models.CharField(max_length=32, blank=True)
    listing_base_price = models.IntegerField(null=True, blank=True, default=None)
    listing_base_price_accurate = models.CharField(max_length=32, blank=True)
    listing_host_fee_accurate = models.CharField(max_length=32, blank=True)
    listing_cancellation_host_fee_accurate = models.CharField(max_length=32, blank=True)
    listing_cancellation_payout_accurate = models.CharField(max_length=32, blank=True)
    listing_security_price_accurate = models.CharField(max_length=32, blank=True)
    occupancy_tax_amount_paid_to_host_accurate = models.CharField(max_length=32, blank=True)
    listing_cleaning_fee_accurate = models.CharField(max_length=32, blank=True)
    transient_occupancy_tax_paid_amount_accurate = models.CharField(max_length=32, blank=True)
    total_paid_amount_accurate = models.CharField(max_length=32, blank=True)
    standard_fees_details = JSONField(default=[])
    transient_occupancy_tax_details = JSONField(default=[])

    thread_id = models.IntegerField(null=True, default=None)
    is_preconfirmed = models.BooleanField(default=False)
    raw_json = JSONField(default={})
    status_type = models.CharField(
        max_length=32, choices=ReservationStatus.choices(), default=ReservationStatus.new
    )
    cancellation_policy_category = models.CharField(
        max_length=32, choices=CancellationPolicy.choices(), default=CancellationPolicy.flexible
    )


class ReservationPayoutDetails(models.Model):

    expected_payout_amount = models.IntegerField()
    listing_base_price = models.IntegerField()
    listing_cancellation_host_fee = models.IntegerField()
    listing_cancellation_payout = models.IntegerField()
    listing_host_fee = models.IntegerField()
    occupancy_tax_amount_paid_to_host = models.IntegerField()
    transient_occupancy_tax_paid_amount = models.IntegerField()


class AirbnbSync(ChannelSync):

    account = models.ForeignKey(AirbnbAccount, on_delete=models.CASCADE, null=True)
    prop = models.ForeignKey(
        Property, on_delete=models.CASCADE, related_name="airbnb_sync", null=True
    )
    name = "Airbnb"
    url = None

    @property
    def url(self):
        return LISTING_URL_TEMPLATE.format(self.external_id)

    def get_info(self):
        return {"name": "Airbnb", "type": self.channel_type, "status": "listed", "id": 1}

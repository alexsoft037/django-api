from datetime import date
from logging import getLogger

from django.db import models

from accounts.models import Organization
from cozmo_common.enums import ChoicesEnum, IntChoicesEnum
from listings import serializers as l_serializers
from listings.choices import PropertyStatuses
from listings.models import Blocking, Image, Property
from . import services

logger = getLogger(__name__)


class RentalConnection(models.Model):
    class Types(ChoicesEnum):
        Isi = "ISI"
        Escapia = "ESC"

    class Statuses(IntChoicesEnum):
        Enabled = 0
        Disabled = 1
        Hidden = 2

    _services = {
        Types.Isi.value: services.IsiService,
        Types.Escapia.value: services.EscapiaService,
    }

    username = models.CharField(max_length=200, blank=False, default="")
    password = models.CharField(max_length=200, blank=False, default="")
    api_type = models.CharField(max_length=3, choices=Types.choices())
    code = models.CharField(max_length=20, default="", blank=True)
    status = models.SmallIntegerField(choices=Statuses.choices(), default=Statuses.Enabled.value)
    auto_correct = models.BooleanField(default=False)
    api_key = models.CharField(max_length=200, blank=True, default="")
    client_id = models.CharField(max_length=200, blank=True, default="")
    features = models.ManyToManyField("listings.Feature", blank=True)

    organization = models.ForeignKey(Organization, null=True, on_delete=models.CASCADE)
    date_updated = models.DateTimeField(auto_now=True, null=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        permissions = (
            ("public_api_access", "Can access data in Public API"),
            ("view_rentalconnection", "Can view rental connections"),
        )

    @property
    def service(self):
        if not hasattr(self, "_service"):
            try:
                service_class = self._services[self.api_type]
            except KeyError:
                raise ValueError(f'No such service type: "{self.api_type}"')
            self._service = service_class(self.username, self.password, self.code)
        return self._service

    def sync(self, external_id: str):
        listing = self.service.get_listing(external_id)
        self._sync_update([listing])

    def log(self, status, message=""):
        SyncLog.objects.create(status=status.value, rental_connection=self, message=message)

    def _sync_initial(self):
        listings = self.service.get_listings()
        serializer = l_serializers.PropertyCreateSerializer(
            data=list(map(self.service.to_cozmo_property, listings)),
            many=True,
            context={"organization": self.organization},
        )
        serializer.is_valid(raise_exception=True)

        cozmo_listings = serializer.save(rental_connection=self)
        ids = (l.external_id for l in cozmo_listings)
        reservations = map(self.service.get_reservations, ids)

        Blocking.objects.bulk_create(
            Blocking(prop=prop, time_frame=res)
            for prop, prop_reservations in zip(cozmo_listings, reservations)
            for res in prop_reservations
        )

    def _set_disabled(self, listings):
        """
        get listing ids from source A
        get listing ids from current list B
        get difference of A from B a.diffrence(b)
        set those listings to Disabled

        reenable if it shows up again instead of creating new
        :param listings:
        :return:
        """
        source_ext_prop_ids = set([l["external_id"] for l in listings])
        current_ext_prop_ids = set(
            Property.objects.filter(rental_connection=self).values_list("external_id", flat=True)
        )
        diff = current_ext_prop_ids.difference(source_ext_prop_ids)
        Property.objects.filter(
            external_id__in=diff,
            rental_connection=self
        ).update(
            status=PropertyStatuses.Disabled.value,
        )

    def _sync_update(self, listings=None):
        if listings is None:
            listings = self.service.get_listings()
        properties = [self.service.to_cozmo_property(listing) for listing in listings]
        # for listing_data in map(self.service.to_cozmo_property, listings):
        for listing_data in properties:
            self._update_listing(listing_data)

        # self._set_disabled(properties)

    def _create_related_models(self, instance, listing_data):
        Image.objects.filter(prop=instance).delete()
        images = l_serializers.ImageUrlSerializer(many=True)
        images.create(listing_data.get("images", []), prop=instance)

        today = date.today()
        Blocking.objects.filter(prop=instance, time_frame__contained_by=(today, None)).delete()
        Blocking.objects.bulk_create(
            Blocking(prop=instance, time_frame=(start, end))
            for (start, end) in self.service.get_reservations(instance.external_id)
            if start >= today
        )

    def _update_listing(self, listing_data: dict):
        external_id = listing_data["external_id"]
        kwargs = {"data": listing_data, "context": {"organization": self.organization}}

        try:
            serializer_class = l_serializers.PropertyUpdateSerializer
            kwargs["instance"] = Property.objects.get(
                external_id=external_id,
                organization_id=self.organization_id,
                status=PropertyStatuses.Active.value,
            )
        except Property.DoesNotExist:
            serializer_class = l_serializers.PropertyCreateSerializer
        except Property.MultipleObjectsReturned:
            logger.info(
                "Connection update failed, external_id not unique in org: id=%s, external_id=%s",
                self.id,
                external_id,
            )
            return

        serializer = serializer_class(**kwargs)
        if not serializer.is_valid():
            logger.warning(
                "Connection update failed, validation error: id=%s, external_id=%s, errors=%s",
                self.id,
                external_id,
                serializer.errors,
            )
            return
        cozmo_listing = serializer.save(rental_connection=self, external_id=external_id)
        self._create_related_models(cozmo_listing, listing_data)


class SyncLog(models.Model):
    class Statuses(ChoicesEnum):
        Synced = 0
        Syncing = 1
        Error = 2

    status = models.PositiveSmallIntegerField(choices=Statuses.choices())
    message = models.CharField(max_length=200, default="", blank=True)
    rental_connection = models.ForeignKey(
        RentalConnection, on_delete=models.CASCADE, related_name="logs"
    )

    date_updated = models.DateTimeField(auto_now=True, null=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)

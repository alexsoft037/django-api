from logging import getLogger

from django.db.models import F
from rest_framework import serializers

from cozmo_common.fields import ChoicesField, DefaultOrganization
from listings.models import Property
from rental_integrations.serializers import AccountSerializer
from . import models

logger = getLogger(__name__)


class ListingSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Listing
        fields = ("pk", "name", "image", "address")


class BookingAccountSerializer(AccountSerializer, serializers.ModelSerializer):

    listings = ListingSerializer(source="listing_set", many=True, read_only=True)
    organization = serializers.HiddenField(default=DefaultOrganization())

    class Meta:
        model = models.BookingAccount
        fields = ("id", "user_id", "secret", "listings", "organization")


class ImportSerializer(serializers.ModelSerializer):

    secret = serializers.CharField(required=False, write_only=True)
    listings = serializers.PrimaryKeyRelatedField(
        many=True, source="listing_set", queryset=models.Listing.objects.all()
    )

    class Meta:
        model = models.BookingAccount
        fields = ("secret", "listings")


class FetchSerializer(serializers.Serializer):
    @property
    def data(self):
        mapped_ids = (
            self.instance.organization.property_set.annotate(booking_id=F("booking__external_id"))
            .exclude(booking_id=None)
            .values_list("booking_id", flat=True)
        )
        _, listings = self.instance.service.get_listings()

        return [
            listing
            for listing in listings
            if f"{self.instance.channel_type}:{listing['id']}" not in mapped_ids
        ]


class WebhookHandler:
    def __init__(self, action, validated_data):
        self._action = {
            "import": self._import,
            "export": self._export,
            "link": self._link,
            "unlink": self._unlink,
        }.get(action, self._unlink)

        self.validated_data = validated_data
        self.external_id = validated_data["booking_id"]
        self.app = validated_data["booking_app"]

    def __call__(self):
        self._action()

    def _import(self):
        self.app.import_listings()

    def _export(self):
        _, content = self.app.service.push_listing(self.validated_data["id"])
        try:
            self.external_id = content.find("./UniqueID", namespaces=content.nsmap).get("ID")
        except AttributeError:
            logger.warn("Booking.com: could not push property %s", self.validated_data["id"])
        else:
            models.BookingSync.objects.update_or_create(
                prop=self.validated_data["id"],
                organization=self.app.organization,
                defaults={"external_id": self.external_id, "sync_enabled": True},
            )

    def _link(self):
        models.BookingSync.objects.update_or_create(
            external_id=self.external_id,
            organization=self.app.organization,
            defaults={"prop": self.validated_data["id"], "sync_enabled": True},
        )

    def _unlink(self):
        models.BookingSync.objects.filter(
            external_id=self.external_id, organization=self.app.organization
        ).delete()


class LinkSerializer(serializers.Serializer):

    does_not_exist_error = "Does not exist"

    id = serializers.PrimaryKeyRelatedField(queryset=Property.objects.active(), allow_null=True)
    booking_id = serializers.CharField(allow_null=True)
    booking_app = serializers.PrimaryKeyRelatedField(queryset=models.BookingAccount.objects.all())
    organization = serializers.HiddenField(default=DefaultOrganization())
    action = ChoicesField(
        choices=(
            ("import", "import"),
            ("export", "export"),
            ("link", "link"),
            ("unlink", "unlink"),
        ),
        required=False,
        allow_null=True,
        default=None,
    )

    def validate(self, data):
        prop = data["id"]
        organization = data["organization"]
        booking_app = data["booking_app"]
        if prop is None:
            if data["booking_id"] is None:
                raise serializers.ValidationError("Set at least one of: 'id', 'booking_id'")
        elif prop.organization != organization:
            raise serializers.ValidationError({"id": self.does_not_exist_error})

        if booking_app is None or booking_app.organization != organization:
            raise serializers.ValidationError({"booking_app": self.does_not_exist_error})

        if data["action"] is None:
            if data["id"] and data["booking_id"]:
                data["action"] = "link"
            elif data["id"] and not data["booking_id"]:
                data["action"] = "export"
            elif not data["id"] and data["booking_id"]:
                data["action"] = "import"
        return data

    def create(self, validated_data):
        booking_id = validated_data["booking_id"]

        handler = WebhookHandler(validated_data["action"], validated_data)
        handler()

        if booking_id:
            pass  # TODO Push reservations

        validated_data["id"].save()

        return {
            name: self.fields[name].to_representation(value)
            for name, value in validated_data.items()
            if not self.fields[name].write_only
        }

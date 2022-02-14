import logging

from django.db.models import F
from rest_framework import serializers
from rest_framework.fields import HiddenField

from cozmo_common.fields import ChoicesField, DefaultOrganization, PositiveSmallIntegerChoicesField
from listings.models import Property
from listings.serializers import PropertyCreateSerializer
from rental_integrations.choices import ListingStatus
from rental_integrations.serializers import AccountSerializer, ChannelSyncSerializer
from rental_integrations.trip_advisor.models import Listing, TripAdvisorSync
from rental_integrations.trip_advisor.service_serializers import camelize
from . import models

logger = logging.getLogger(__name__)


class ListingSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Listing
        fields = ("pk", "name", "image", "address")


class TripAdvisorAccountSerializer(AccountSerializer, serializers.ModelSerializer):
    serializer_choice_field = PositiveSmallIntegerChoicesField

    listings = ListingSerializer(source="listing_set", many=True, read_only=True)
    organization = HiddenField(default=DefaultOrganization())

    class Meta:
        model = models.TripAdvisorAccount
        fields = ("id", "user_id", "listings", "organization", "status")


class ImportSerializer(serializers.ModelSerializer):

    listings = serializers.PrimaryKeyRelatedField(
        many=True, source="listing_set", queryset=models.Listing.objects.all()
    )

    class Meta:
        model = models.TripAdvisorAccount
        fields = ("listings",)


# class TripAdvisorSyncSerializer(serializers.ModelSerializer):
#
#     organization = HiddenField(default=DefaultOrganization())
#
#     class Meta:
#         model = models.TripAdvisorSync
#         fields = "__all__"
#         read_only_fields = "external_id", "prop"


class FetchSerializer(serializers.Serializer):
    @property
    def data(self):
        mapped_ids = (
            self.instance.organization.property_set.annotate(
                ta_id=F("tripadvisor_sync__external_id")
            )
            .exclude(ta_id=None)
            .values_list("ta_id", flat=True)
        )
        listings = self.instance.service.get_listings()

        return [
            {
                "id": listing["external_listing_reference"],
                "name": listing["descriptions"]["listing_title"],
                "bedrooms": "",
                "bathrooms": "",
                "street": listing["address"]["address"],
                "apartment": "",
                "city": listing["location"]["city"],
                "state": listing["location"]["region"],
                "zipcode": listing["address"]["postal_code"],
                "latitude": listing["address"]["latitude"],
                "longitude": listing["address"]["longitude"],
                "country_code": listing["location"]["country_code"],
                "full_address": listing["address"]["address"],
                "listed": listing["active"],
                "cover_image": listing["photos"][0]["url"] if listing["photos"] else None,
            }
            for listing in listings
            if f"{self.instance.channel_type}:{listing['external_listing_reference']}"
            not in mapped_ids
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
        self.external_id = validated_data["channel_id"]
        self.app = validated_data["channel_app"]

    def __call__(self):
        self._action()

    def _import(self):
        service = self.app.service
        listing = service.get_listing(self.external_id)

        ta_listing = Listing(owner=self.app, data=camelize(listing))

        serializer = PropertyCreateSerializer(
            data=ta_listing._to_cozmo(), context=self.validated_data
        )
        if serializer.is_valid():
            self.validated_data["id"] = serializer.save()
            ta_listing.save()
            self._link(url=ta_listing.url, active=ta_listing.active)
        else:
            logger.warning("Could not fetch from Airbnb")

    def _export(self):
        _, content = self.app.service.push_listing(self.validated_data["id"])
        try:
            self.external_id = content.find("./UniqueID", namespaces=content.nsmap).get("ID")
        except AttributeError:
            logger.warn("Tripadvisor: could not push property %s", self.validated_data["id"])
        else:
            self._link()

    def _link(self, url="", active=False):
        """
        * Must meet tripadvisor requirements
        * Triggers a link action
            - For Airbnb, that asks Airbnb to review
            - For tripadvisor, it is nil
        * optionally set to live if not already
        """
        models.TripAdvisorSync.objects.create(
            prop=self.validated_data["id"],
            external_id=self.external_id,
            organization=self.app.organization,
            sync_enabled=True,
            url=url,
            account=self.app,
            status=ListingStatus.listed if active else ListingStatus.unlisted,
        )

    def _unlink(self):
        models.TripAdvisorSync.objects.filter(
            external_id=self.external_id, organization=self.app.organization
        )


class LinkSerializer(serializers.Serializer):

    does_not_exist_error = "Does not exist"

    id = serializers.PrimaryKeyRelatedField(queryset=Property.objects.active(), allow_null=True)
    channel_id = serializers.CharField(allow_null=True)
    channel_app = serializers.PrimaryKeyRelatedField(
        queryset=models.TripAdvisorAccount.objects.all()
    )
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
        channel_app = data["channel_app"]
        if prop is None:
            if data["channel_id"] is None:
                raise serializers.ValidationError("Set at least one of: 'id', 'channel_id'")
        elif prop.organization != organization:
            raise serializers.ValidationError({"id": self.does_not_exist_error})

        if channel_app is None or channel_app.organization != organization:
            raise serializers.ValidationError({"channel_app": self.does_not_exist_error})

        if data["action"] is None:
            if data["id"] and data["channel_id"]:
                data["action"] = "link"
            elif data["id"] and not data["channel_id"]:
                data["action"] = "export"
            elif not data["id"] and data["channel_id"]:
                data["action"] = "import"
        return data

    def create(self, validated_data):
        channel_id = validated_data["channel_id"]

        handler = WebhookHandler(validated_data["action"], validated_data)
        handler()

        if channel_id:
            pass  # TODO Push reservations

        if validated_data["id"]:
            validated_data["id"].save()
        else:
            validated_data.pop("id")

        return {
            name: self.fields[name].to_representation(value)
            for name, value in validated_data.items()
            if not self.fields[name].write_only
        }


class TripAdvisorSyncSerializer(ChannelSyncSerializer):
    class Meta(ChannelSyncSerializer.Meta):
        model = TripAdvisorSync

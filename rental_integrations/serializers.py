from rest_framework import serializers
from rest_framework.fields import HiddenField, SerializerMethodField

from cozmo_common.fields import DefaultOrganization
from rental_integrations.choices import (
    ChannelType,
    ListingApprovalStatus,
    ListingStatus,
    ListingSyncScope,
)
from rental_integrations.models import ChannelSync
from . import models


class IntegrationSettingSerializer(serializers.ModelSerializer):
    organization = serializers.HiddenField(default=DefaultOrganization())

    class Meta:
        model = models.IntegrationSetting
        fields = "__all__"


class SecretSerializer(serializers.Serializer):

    secret = serializers.CharField(required=False, write_only=True)
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())


class AccountSerializer(serializers.Serializer):

    secret = serializers.CharField(required=False, write_only=True)
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    def create(self, validated_data):
        secret = validated_data.pop("secret", None)
        instance = super().create(validated_data)
        if secret:
            instance.update_listings(secret)
        return instance


class ChannelSyncBasicSerializer(serializers.Serializer):

    app_id = serializers.IntegerField(source="account_id")
    id = serializers.IntegerField()
    external_id = serializers.CharField()
    last_sync = serializers.DateTimeField()
    date_updated = serializers.DateTimeField()
    date_created = serializers.DateTimeField()
    status = serializers.ChoiceField(choices=ListingStatus.choices())
    approval_status = serializers.ChoiceField(choices=ListingApprovalStatus.choices())
    scope = serializers.ChoiceField(choices=ListingSyncScope.choices())
    url = serializers.URLField()
    name = serializers.CharField()


class ChannelSyncSerializer(serializers.ModelSerializer):

    # info = SerializerMethodField()
    organization = HiddenField(default=DefaultOrganization())
    name = SerializerMethodField()
    url = SerializerMethodField()
    min_requirements = SerializerMethodField()

    class Meta:
        model = ChannelSync
        fields = (
            "prop",
            # "info",
            "id",
            "external_id",
            "organization",
            "sync_enabled",
            "last_sync",
            "status",
            "name",
            "approval_status",
            "scope",
            "url",
            "date_updated",
            "date_created",
            "min_requirements",
        )

    def get_min_requirements(self, obj):
        # req_map = {
        #     ChannelType.airbnb.value: AirbnbListingReviewSerializer
        # }
        # serializer = req_map.get(obj.channel_type)(data=obj.prop.image_set)
        # if serializer:
        #     serializer.is_valid()
        #     return serializer.error_messages

        return None

    def get_url(self, obj):
        url_template = {
            ChannelType.airbnb.value: f"https://www.airbnb.com/rooms/{obj.external_id}",
            ChannelType.tripadvisor.value: "https://www.rentals.tripadvisor.com/TODO",
        }
        return url_template.get(obj.channel_type, None)

    def get_name(self, obj):
        if obj.channel_type == ChannelType.tripadvisor.value:
            return "Tripadvisor"
        if obj.channel_type == ChannelType.airbnb.value:
            return "Airbnb"
        return "Not Set"

    # def get_info(self, obj):
    #     return obj.get_info()


class BaseListingReviewSerializer(serializers.Serializer):
    """
    This is the base serializer for checking if a listing meets min requirements for
    a corresponding channel
    """

    photos = serializers.ListField()

    def validate_photos(self, photos):
        """
        Should validate if photos have min size and number requirements
        """
        raise NotImplementedError()

    def validate_permits(self, permit):
        """
        Should validate if listing has permit requirements
        """
        raise NotImplementedError()

    def validate_amenities(self, amenities):
        """
        Should validate if listing has enough and/or has required amenities
        """
        raise NotImplementedError()

    def validate_description(self, description):
        """
        Should validate if listing has sufficient description content
        """
        raise NotImplementedError()

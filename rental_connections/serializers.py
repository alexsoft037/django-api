from rest_framework import serializers
from rest_framework.fields import HiddenField

from cozmo_common.fields import ChoicesField, DefaultOrganization
from listings.choices import PropertyStatuses
from listings.models import Feature
from rental_integrations.exceptions import ServiceException
from . import models
from .tasks import rental_connection_sync


class SyncLogSerializer(serializers.ModelSerializer):

    serializer_choice_field = ChoicesField

    class Meta:
        model = models.SyncLog
        fields = ("status", "message", "date")
        extra_kwargs = {"date": {"source": "date_created"}}


class RentalConnectionSerializer(serializers.ModelSerializer):

    organization = HiddenField(default=DefaultOrganization())
    properties = serializers.SerializerMethodField()
    synced_properties = serializers.SerializerMethodField()
    last_sync = serializers.SerializerMethodField()
    logs = serializers.SerializerMethodField()

    serializer_choice_field = ChoicesField

    class Meta:
        model = models.RentalConnection
        exclude = ["date_updated", "date_created"]
        extra_kwargs = {
            "password": {"write_only": True, "required": True},
            "username": {"required": True},
            "status": {"default": models.RentalConnection.Statuses.Disabled},
        }

    def validate(self, attrs):
        if self.instance:
            instance = self.instance
        else:
            instance = models.RentalConnection(**attrs)

        if not instance.service.perform_check_request():
            raise serializers.ValidationError("Invalid Credentials provided")
        return super().validate(attrs)

    def get_properties(self, instance):
        try:
            listings = instance.service.get_listings_count() or 0
        except ServiceException:
            listings = 0
        return listings

    def get_synced_properties(self, instance):
        return instance.property_set.count()

    def get_last_sync(self, instance):
        log = instance.logs.last()
        if log:
            data = SyncLogSerializer(instance=log).data
        else:
            data = {}

        return data

    def get_logs(self, instance):
        logs = instance.logs.order_by("-id")[:3]
        return SyncLogSerializer(instance=logs, many=True).data

    def schedule_sync(self, initial=False):
        self.instance.log(models.SyncLog.Statuses.Syncing)
        rental_connection_sync.s(self.instance.id, initial).apply_async()

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        new_status = validated_data.get("status")
        if new_status == models.RentalConnection.Statuses.Enabled:
            count = instance.property_set.update(status=PropertyStatuses.Active)
            initial = count == 0
            self.schedule_sync(initial=initial)
        elif new_status == models.RentalConnection.Statuses.Disabled:
            instance.property_set.update(status=PropertyStatuses.Disabled)
        elif new_status == models.RentalConnection.Statuses.Hidden:
            instance.property_set.update(status=PropertyStatuses.Removed)
        return instance


class FeatureSerializer(serializers.ModelSerializer):

    serializer_choice_field = ChoicesField

    class Meta:
        model = Feature
        fields = "__all__"

        extra_kwargs = {"name": {"read_only": True}}

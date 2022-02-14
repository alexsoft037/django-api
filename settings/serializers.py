from rest_framework import serializers

from settings.models import OrganizationSettings


class OrganizationSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationSettings
        fields = ("channel_network_enabled",)

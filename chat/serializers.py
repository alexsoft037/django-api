from rest_framework.serializers import ModelSerializer

from chat.models import Settings


class ChatSettingsSerializer(ModelSerializer):

    class Meta:
        model = Settings
        exclude = (
            "id",
            "date_created",
            "date_updated",
            "org_settings"
        )
        extra_kwargs = {"org_settings": {"write_only": True}}

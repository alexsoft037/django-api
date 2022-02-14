from logging import getLogger

from rest_framework import serializers
from rest_framework.fields import CharField, HiddenField

from cozmo_common.fields import DefaultOrganization
from send_mail.phone.models import Number

logger = getLogger(__name__)


class NumberSerializer(serializers.ModelSerializer):
    organization = HiddenField(default=DefaultOrganization())

    class Meta:
        model = Number
        fields = "__all__"


class NumberSearchSerializer(serializers.Serializer):
    organization = HiddenField(default=DefaultOrganization())
    country_code = CharField()
    capabilities = CharField(default="SMS")
    phone_type = CharField(required=False)
    pattern = CharField()

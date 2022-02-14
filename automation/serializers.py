import logging
import re

from rest_framework import serializers
from rest_framework.relations import PrimaryKeyRelatedField

from automation.choices import RecipientType
from automation.errors import NoRecipientAddressValidationError
from automation.models import ReservationAutomation
from cozmo_common.fields import DefaultOrganization
from listings.serializers import PropertySerializer, ReservationSerializer
from message_templates.models import Template
from message_templates.serializers import TemplateSerializer

logger = logging.getLogger(__name__)


class ReservationAutomationSerializer(serializers.ModelSerializer):

    organization = serializers.HiddenField(default=DefaultOrganization())
    template = PrimaryKeyRelatedField(
        queryset=Template.objects.all(), required=False, allow_null=True
    )
    recipient_address = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    cc_address = serializers.ListField(
        child=serializers.EmailField(), allow_empty=True, required=False, allow_null=True
    )
    bcc_address = serializers.ListField(
        child=serializers.EmailField(), allow_empty=True, required=False, allow_null=True
    )

    def validate(self, data):
        if data["recipient_type"] == RecipientType.email.value and not data.get(
            "recipient_address"
        ):
            raise NoRecipientAddressValidationError()
        return data

    class Meta:
        model = ReservationAutomation
        fields = (
            "is_active",
            "days_delta",
            "event",
            "time",
            "method",
            "recipient_type",
            "organization",
            "template",
            "recipient_address",
            "cc_address",
            "bcc_address",
            "id",
        )
        extra_kwargs = {"organization": {"write_only": True}}


class RenderTemplateSerializer(serializers.Serializer):

    template = TemplateSerializer()
    prop = PropertySerializer()
    reservation = ReservationSerializer()

    def get_variable_value(self, root, keys):
        """
        Grabs the variable (should we try using eval?
        :param root: object with attributes
        :param keys: list of keys that were spllit from a '.' delimited string
        :return:
        """
        value = getattr(root, keys[0]) if not isinstance(root, dict) else root.get(keys[0])
        if len(keys) == 1:
            return value
        return self.get_variable_value(value, keys[1:])

    def _get_variables(self, content):
        pattern = re.compile("{(\w+[a-zA-Z._]*)}")
        matches = pattern.findall(content)
        return matches

    def _replace_variables(self, data):
        """
        Replaces variables inside template
        :param data:
        :return:
        """
        template = data["template"]
        prop = data["prop"]
        reservation = data["reservation"]
        root = {"template": template, "property": prop, "reservation": reservation}
        content = template.get_content()
        variables = self._get_variables(content)
        keys = dict()
        for var in variables:
            # TODO validate each variable is legal
            value = self.get_variable_value(root, var.split("."))
            keys[var] = value
        return content.format(**keys)

    def create(self, validated_data):
        return self._replace_variables(validated_data)

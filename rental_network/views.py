import re

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK
from rest_framework.viewsets import GenericViewSet

from rental_network.models import Account


class VerificationNotificationSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=12)
    content = serializers.CharField(max_length=144)
    code = serializers.SerializerMethodField()

    def validate_content(self, content):
        if "apartments.com" not in content.lower():
            raise ValidationError()
        pattern = re.compile("[A-Z0-9]{4}")
        match = pattern.findall(content)
        if not match:
            raise ValidationError()
        return content

    def get_code(self, object):
        pattern = re.compile("[A-Z0-9]{4}")
        match = pattern.findall(object["content"])
        return match[0] if match else None


class VerificationNotificationViewSet(GenericViewSet):

    permission_classes = (AllowAny,)
    lookup_field = "confirmation_code"
    serializer_class = VerificationNotificationSerializer

    def create(self, request, *args, **kwargs):
        """Airbnb Reservation webhook"""
        # 76.103.90.181
        # 4152995346
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            Account.objects.filter(two_factor_phone=serializer.data.get("phone")).update(
                last_verification_code=serializer.data.get("code")
            )

        return Response(status=HTTP_200_OK)

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK

from cozmo_common.filters import OrganizationFilter
from cozmo_common.mixins import ApplicationPermissionViewMixin
from settings.models import OrganizationSettings
from . import serializers


class OrganizationSettingsViewSet(ApplicationPermissionViewMixin, viewsets.GenericViewSet):
    """Read, create, update and delete Org Settings"""

    queryset = OrganizationSettings.objects.all()
    serializer_class = serializers.OrganizationSettingsSerializer
    filter_backends = (OrganizationFilter,)
    search_fields = ("channel_network_enabled",)

    @action(detail=False, methods=["PATCH", "GET"])
    def organization(self, request, *args, **kwargs):
        if request.method == "GET":
            instance, _ = self.queryset.get_or_create(organization=request.user.organization)
            serializer = self.get_serializer(instance=instance)
            return Response(status=HTTP_200_OK, data=serializer.data)
        else:
            instance, _ = self.queryset.get_or_create(organization=request.user.organization)
            serializer = self.get_serializer(instance=instance, data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(status=HTTP_200_OK, data=serializer.validated_data)

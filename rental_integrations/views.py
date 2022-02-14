from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from cozmo_common.filters import OrganizationFilter
from . import models, serializers


class BaseAccountViewSet:
    """Read, create, update and delete Integration with rental service."""

    filter_backends = (OrganizationFilter,)

    def perform_create(self, serializer):
        """Create instance based on provieded data plus current user."""
        serializer.save(organization=self.request.user.organization)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return self.get_response() or response

    def get_response(self):
        raise NotImplementedError()

    @action(detail=True, methods=["POST"], url_path="import")
    def import_listings(self, request, pk):
        data = []
        return Response(status=status.HTTP_200_OK, data=data)

    @action(detail=True, methods=["POST"])
    def fetch(self, request, pk):
        raise NotImplementedError()

    @action(detail=True, methods=["PATCH"], url_path="listings")
    def update_listings(self, request, pk):
        raise NotImplementedError()


class IntegrationViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):

    filter_backends = (OrganizationFilter,)

    @action(detail=True, methods=["POST"], serializer_class=serializers.SecretSerializer)
    def fetch(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = self.get_object()
        instance.update_listings(serializer.initial_data["secret"])
        instance.update_reservations(secret=serializer.initial_data["secret"])

        return Response(data=type(self).serializer_class(instance=instance).data)

    @action(detail=True, methods=["POST"], url_path="import", serializer_class=NotImplementedError)
    def import_listings(self, request, pk):
        instance = self.get_object()
        serializer = self.get_serializer(instance=instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        instance.import_listings(ids=serializer.initial_data["listings"])
        return Response(data=serializer.initial_data)

    @action(detail=True, methods=["PATCH"], url_path="listings")
    def update_listings(self, request, pk):
        raise NotImplementedError()


class IntegrationSettingViewSet(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):

    queryset = models.IntegrationSetting.objects.all()
    serializer_class = serializers.IntegrationSettingSerializer
    filter_backends = (OrganizationFilter,)

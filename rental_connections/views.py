from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.serializers import Serializer as EmptySerializer
from rest_framework.status import HTTP_202_ACCEPTED

from cozmo_common.filters import OrganizationFilter
from cozmo_common.mixins import ApplicationPermissionViewMixin
from . import models, serializers


class RentalConnectionViewSet(ApplicationPermissionViewMixin, viewsets.ModelViewSet):
    """Read, create, update and delete RentalConnection"""

    queryset = models.RentalConnection.objects.all()
    filter_backends = (OrganizationFilter,)
    serializer_class = serializers.RentalConnectionSerializer

    @action(detail=True, methods=["POST"], serializer_class=EmptySerializer)
    def sync(self, request, pk):
        instance = self.get_object()
        serializer = RentalConnectionViewSet.serializer_class(instance=instance)
        serializer.schedule_sync()
        return Response(data=serializer.data, status=HTTP_202_ACCEPTED)

    @action(detail=True, methods=["GET"])
    def feature_map(self, request, pk):
        obj = self.get_object()
        serializer = serializers.FeatureSerializer(
            obj.features.filter(organization=obj.organization), many=True
        )
        return Response(data=serializer.data)

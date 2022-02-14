from django.conf import settings
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK
from rest_framework.viewsets import GenericViewSet

from cozmo_common.filters import OrganizationFilter
from listings.models import Property
from listings.serializers import PropertySerializer
from rental_integrations.trip_advisor.service import TripAdvisorClient
from rental_integrations.trip_advisor.tasks import update_or_create_listings
from rental_integrations.views import IntegrationViewSet
from . import serializers
from .models import TripAdvisorAccount


class TripAdvisorViewSet(IntegrationViewSet):

    queryset = TripAdvisorAccount.objects.all()
    serializer_class = serializers.TripAdvisorAccountSerializer

    @action(
        detail=True,
        methods=["POST"],
        url_path="import",
        serializer_class=serializers.ImportSerializer,
    )
    def import_listings(self, request, pk):
        return super().import_listings(request, pk)

    @action(detail=True, methods=["GET"], serializer_class=serializers.FetchSerializer)
    def fetch(self, request, pk):
        serializer = self.get_serializer(instance=self.get_object())
        return Response(data=serializer.data, status=HTTP_200_OK)

    @action(detail=False, methods=["POST"], serializer_class=serializers.LinkSerializer)
    def link(self, request):
        """
        Match Cozmo properties with Booking.com listings.

        Handles links, unlinks, imports and exports.
        """
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.save()
        return Response(data=data, status=HTTP_200_OK)


class TripAdvisorSyncViewSet(GenericViewSet):
    """
    Cozmo Sync TripAdvisor ViewSet
    """

    queryset = Property.objects.all().order_by("id")
    serializer_class = serializers.TripAdvisorSyncSerializer
    filter_backends = (OrganizationFilter,)

    @action(detail=True, methods=["PATCH"])
    def change_sync_enabled(self, request, *args, **kwargs):
        instance = self.get_object()
        if hasattr(instance, "tripadvisor"):
            serializer = self.get_serializer(instance.tripadvisor, data=request.data, partial=True)
        else:
            serializer = self.get_serializer(data={**request.data, "prop": instance})

        serializer.is_valid(raise_exception=True)
        serializer.save(prop=instance)
        return Response(serializer.data)

    @action(detail=True, methods=["POST"])
    def push_property(self, request, pk):
        instance = self.get_object()

        client = TripAdvisorClient(settings.TRIPADVISOR_CLIENT_ID, settings.TRIPADVISOR_SECRET_KEY)
        status_code, errors = client.push_listing(instance)
        if status_code == 200:
            return Response(status=status_code, data=PropertySerializer(instance).data)
        return Response(status=status_code, data=errors)

    @action(detail=False, methods=["POST"])
    def push_properties(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        update_or_create_listings.s(
            [id for id in queryset.values_list("id", flat=True)]
        ).apply_async()
        return Response({"message": "The properties were schedule to the synchronization"})

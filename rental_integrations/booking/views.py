from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK

from rental_integrations.views import IntegrationViewSet
from . import serializers
from .models import BookingAccount


class BookingViewSet(IntegrationViewSet):

    queryset = BookingAccount.objects.all()
    serializer_class = serializers.BookingAccountSerializer

    @action(
        detail=True,
        methods=["POST"],
        url_path="import",
        serializer_class=serializers.ImportSerializer,
    )
    def import_listings(self, request, pk):
        return super().import_listings(request, pk)

    # @action(detail=True, methods=["GET"], serializer_class=ReservationSerializer)
    # def reservations(self, request, pk):
    #     """Fetch and return listings from Booking.com"""
    #     from rental_integrations.booking.service import BookingXmlClient
    #     import os
    #
    #     USER = os.environ.get("BOOKING_CLIENT_USERNAME")
    #     PASSWORD = os.environ.get("BOOKING_CLIENT_SECRET")
    #
    #     service = BookingXmlClient(USER, PASSWORD)
    #     service.get_reservations()
    # serializer = self.get_serializer(instance=self.get_object())
    # return Response(data=serializer.data, status=HTTP_200_OK)

    @action(detail=True, methods=["GET"], serializer_class=serializers.FetchSerializer)
    def fetch(self, request, pk):
        """Fetch and return listings from Booking.com"""
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

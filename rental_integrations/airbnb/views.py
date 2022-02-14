import logging

from django.http import Http404
from requests import HTTPError
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK
from rest_framework.viewsets import ReadOnlyModelViewSet

from app_marketplace.choices import AirbnbListingStatus
from app_marketplace.services import Airbnb
from cozmo_common.mixins import ModelPermissionsMixin
from rental_integrations.airbnb.models import AirbnbAccount
from rental_integrations.airbnb.serializers import sync_reservations
from . import serializers
from .service import AirbnbService

logger = logging.getLogger(__name__)


class AirbnbViewSet(ModelPermissionsMixin, ReadOnlyModelViewSet):

    serializer_class = serializers.AirbnbAppDetailedSerializer
    queryset = AirbnbAccount.objects.all()

    def get_object_organization(self, obj):
        return obj.organization

    @action(detail=True, methods=["POST"], serializer_class=serializers.AuthRequestSerializer)
    def refresh_token(self, request, pk):
        app = self.get_object()
        airbnb = Airbnb()
        try:
            response = airbnb.refresh_token(app.refresh_token)
            app.access_token = response["access_token"]
            app.refresh_token = response.get("refresh_token", app.refresh_token)
            app.user_id = response["user_id"]
            app.save()
            return Response(data=response, status=HTTP_200_OK)
        except HTTPError as e:
            return Response(status=e.response.status_code)

    @action(detail=True, methods=["POST"], serializer_class=serializers.AuthRequestSerializer)
    def revoke_token(self, request, pk):
        app = self.get_object()
        airbnb = Airbnb()
        response = airbnb.revoke_token(app.access_token)
        app.property_set.update(airbnb_sync=None)
        app.listing_set.all().delete()
        app.airbnb_user.delete()
        app.delete()
        return Response(data=response, status=HTTP_200_OK)

    @action(detail=True, methods=["POST"], serializer_class=serializers.AuthRequestSerializer)
    def check_token(self, request, pk):
        app = self.get_object()
        airbnb = Airbnb()
        response = airbnb.check_token(app.access_token)
        return Response(data=dict(valid=response), status=HTTP_200_OK)

    @action(detail=True, methods=["POST"], serializer_class=serializers.AirbnbActionSerializer)
    def update_listing(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        app = self.get_object()
        property = serializer.validated_data["prop_id"]
        service = AirbnbService(app.user_id, app.access_token)

        listing = service.update_listing(service.to_airbnb(property))  # TODO
        service.push_review_status(listing["id"])
        return Response(status=HTTP_200_OK)

    @action(detail=True, methods=["POST"], serializer_class=serializers.AirbnbActionSerializer)
    def delete(self, request, pk):
        """
        Immediately delete an Airbnb listing corresponding to a property id
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        app = self.get_object()
        property = serializer.validated_data["prop_id"]
        service = AirbnbService(app.user_id, app.access_token)

        airbnb_sync = property.airbnb_sync.get()
        if airbnb_sync is None:
            raise Http404("No Airbnb listing is associated with this property")

        if service.delete_listing(airbnb_sync.external_id):
            airbnb_sync.delete()
        return Response(status=HTTP_200_OK)

    @action(detail=True, methods=["POST"], serializer_class=serializers.AirbnbActionSerializer)
    def get_reservations(self, request, pk):
        """
        Immediately sync a property
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        app = self.get_object()
        property = serializer.validated_data["prop_id"]
        service = AirbnbService(app.user_id, app.access_token)

        sync_reservations(service, property, serializer.validated_data)
        return Response(status=HTTP_200_OK)

    @action(detail=True, methods=["POST"], serializer_class=serializers.SyncSerializer)
    def sync(self, request, pk):
        """
        Immediately sync a property
        """

        app = self.get_object()
        serializer = self.get_serializer(
            data=request.data, username=app.user_id, access_token=app.access_token
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(status=HTTP_200_OK)  # TODO return 204 and run sync async

    @action(detail=True, methods=["POST"], serializer_class=serializers.AirbnbActionSerializer)
    def unlist(self, request, pk):
        """
        Delist a listed Airbnb listing that corresponds to a property id
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        app = self.get_object()
        property = serializer.validated_data["prop_id"]
        service = AirbnbService(app.user_id, app.access_token)

        airbnb_sync = property.airbnb_sync.get()
        if airbnb_sync is None:
            raise Http404("No Airbnb listing is associated with this property")

        result = service.push_listing_status(airbnb_sync.external_id, False)
        airbnb_sync.status = (
            AirbnbListingStatus.listed
            if result["has_availability"]
            else AirbnbListingStatus.unlisted
        )
        airbnb_sync.save()
        return Response(status=HTTP_200_OK)

    @action(detail=True, methods=["POST"], serializer_class=serializers.AirbnbActionSerializer)
    def relist(self, request, pk):
        """
        Relist a delisted Airbnb listing that corresponds to a property id
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        app = self.get_object()
        property = serializer.validated_data["prop_id"]
        service = AirbnbService(app.user_id, app.access_token)

        airbnb_sync = property.airbnb_sync.get()
        if airbnb_sync is None:
            raise Http404("No Airbnb listing is associated with this property")
        external_id = airbnb_sync.external_id
        service.push_link(external_id)
        result = service.push_listing_review_and_status(external_id, True)
        airbnb_sync.status = (
            AirbnbListingStatus.listed
            if result["has_availability"]
            else AirbnbListingStatus.unlisted
        )
        airbnb_sync.save()
        return Response(status=HTTP_200_OK)

    @action(detail=True, methods=["GET"], serializer_class=serializers.FetchSerializer)
    def fetch(self, request, pk):
        """Fetch and return listings from Airbnb"""
        serializer = self.get_serializer(instance=self.get_object())
        return Response(data=serializer.data, status=HTTP_200_OK)

    @action(detail=False, methods=["POST"], serializer_class=serializers.PropertyIdSerializer)
    def check(self, request):
        """Verify if Properties are valid for Airbnb"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        properties = serializer.validated_data["ids"]

        results = list()
        for p in properties:
            listing_serializer = serializers.ListingSerializer(data=AirbnbService.to_airbnb(p))
            result = {"id": p.id, "errors": list()}
            if not listing_serializer.is_valid():
                errors = listing_serializer.errors
                result["errors"] = errors.keys()
            results.append(result)
        return Response(data=results, content_type="application/json", status=HTTP_200_OK)

    @action(detail=False, methods=["POST"], serializer_class=serializers.LinkSerializer)
    def link(self, request):
        """
        Match Cozmo properties with Airbnb listings.

        Handles links, unlinks, imports and exports.
        """
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.save()
        return Response(data=data, status=HTTP_200_OK)

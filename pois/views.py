from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from . import serializers


class PoiViewSet(GenericViewSet):
    def perform_query(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        businesses = serializer.save()
        return Response({"pois": businesses})

    @action(
        detail=False, methods=["POST"], serializer_class=serializers.YelpAutocompleteSerializer
    )
    def autocomplete(self, request):
        return self.perform_query(request)

    @action(detail=False, methods=["POST"], serializer_class=serializers.YelpSearchSerializer)
    def nearby(self, request):
        return self.perform_query(request)

    @action(detail=False, methods=["POST"], serializer_class=serializers.YelpTopPlacesSerializer)
    def categories(self, request):
        return self.perform_query(request)

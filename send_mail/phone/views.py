import logging

from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from cozmo_common.filters import OrganizationFilter
from cozmo_common.mixins import ModelPermissionsMixin
from notifications.services.sms import NexmoService
from send_mail.phone.filters import NumberSearchFilter
from send_mail.phone.models import Number
from . import serializers

logger = logging.getLogger(__name__)


class NumberViewSet(ModelPermissionsMixin, ModelViewSet):

    serializer_class = serializers.NumberSerializer
    queryset = Number.objects.all()
    filter_backends = (OrganizationFilter,)

    def get_object_organization(self, obj):
        return obj.organization

    @action(detail=False,
            methods=["GET"],
            filter_backends=[NumberSearchFilter],
            serializer_class=serializers.NumberSearchSerializer)
    def search(self, request):
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        service = NexmoService()
        return Response(data=service.search_available_numbers(
            country_code=data["country_code"],
            capabilities=data.get("capabilities"),
            phone_type=data.get("phone_type"),
            pattern=data.get("pattern")
        ))

    # @action(detail=False, methods=["POST"], serializer_class=serializers.AuthRequestSerializer)
    # def purchase(self, request, pk):
    #     app = self.get_object()
    #     airbnb = Airbnb()
    #     response = airbnb.revoke_token(app.access_token)
    #     app.property_set.update(airbnb_sync=None)
    #     app.listing_set.all().delete()
    #     app.airbnb_user.delete()
    #     app.delete()
    #     return Response(data=response, status=HTTP_200_OK)

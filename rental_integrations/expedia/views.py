from rest_framework.decorators import action

from rental_integrations.views import IntegrationViewSet
from . import serializers
from .models import ExpediaAccount


class ExpediaViewSet(IntegrationViewSet):

    serializer_class = serializers.ExpediaAccountSerializer
    queryset = ExpediaAccount.objects.all()

    @action(
        detail=True,
        methods=["POST"],
        url_path="import",
        serializer_class=serializers.ImportSerializer,
    )
    def import_listings(self, request, pk):
        return super().import_listings(request, pk)

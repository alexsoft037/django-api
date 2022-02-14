from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from chat.models import Settings
from chat.serializers import ChatSettingsSerializer
from cozmo_common.filters import OrganizationFilter
from settings.models import OrganizationSettings


class ChatSettingsViewSet(ListModelMixin, GenericViewSet):
    filter_backends = (OrganizationFilter,)
    serializer_class = ChatSettingsSerializer
    queryset = Settings.objects.all()
    org_lookup_field = "org_settings__organization"

    def list(self, request, *args, **kwargs):
        settings, _ = Settings.objects.get_or_create(
            org_settings=OrganizationSettings.objects.get(organization=request.user.organization)
        )

        serializer = self.get_serializer(settings)
        return Response(serializer.data)

    @action(detail=False, methods=["PATCH"], url_path="update")
    def _update(self, request, *args, **kwargs):
        settings, _ = Settings.objects.get_or_create(
            org_settings=OrganizationSettings.objects.get(organization=request.user.organization)
        )
        serializer = self.get_serializer(instance=settings, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)

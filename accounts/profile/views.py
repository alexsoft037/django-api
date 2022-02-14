from django.contrib.auth import get_user_model
from django.http import Http404
from rest_framework import generics, status, viewsets
from rest_framework.mixins import CreateModelMixin
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from accounts.models import Organization
from accounts.profile.filters import TeamFilter
from cozmo_common.filters import OrganizationFilter
from . import serializers
from .models import PaymentSettings, PlanSettings


class AddFeatureView(generics.UpdateAPIView):
    serializer_class = serializers.AddAppSerializer
    queryset = Organization.objects.all()

    def get_object(self):
        return self.request.user.organization


class RemoveFeatureView(generics.UpdateAPIView):
    serializer_class = serializers.RemoveAppSerializer
    queryset = Organization.objects.all()

    def get_object(self):
        return self.request.user.organization


class OrganizationView(generics.RetrieveUpdateAPIView):
    serializer_class = serializers.OrganizationSerializer
    queryset = Organization.objects.all()

    def get_object(self):
        return self.request.user.organization


class SettingsView(generics.CreateAPIView, generics.RetrieveAPIView, generics.UpdateAPIView):

    filter_backends = (OrganizationFilter,)

    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        obj = generics.get_object_or_404(queryset, organization=self.request.user.organization)
        self.check_object_permissions(self.request, obj)
        return obj

    def create(self, request, *args, **kwargs):
        try:
            self.get_object()
        except Http404:
            response = super().create(request, *args, **kwargs)
        else:
            data = {api_settings.NON_FIELD_ERRORS_KEY: ["Setting already exists"]}
            response = Response(data, status=status.HTTP_400_BAD_REQUEST)

        return response

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)


class PlanSettingsView(SettingsView):
    """Reads and creates Plan settings."""

    serializer_class = serializers.PlanSettingsSerializer
    queryset = PlanSettings.objects.all()


class PaymentSettingsView(SettingsView):
    """Reads and creates Payment Schedule settings."""

    serializer_class = serializers.PaymentSettingsSerializer
    queryset = PaymentSettings.objects.all()


class ShadowLoginViewSet(CreateModelMixin, viewsets.GenericViewSet):
    """
    create:
    Returns token for given user

    Valid for 1 hour since creation. Cannot shadow staff users.
    """

    serializer_class = serializers.ShadowLoginSerializer
    permission_classes = (AllowAny,)


class TeamViewSet(viewsets.ModelViewSet):
    queryset = get_user_model().objects.all().order_by("email")
    serializer_class = serializers.TeamSerializer
    filter_backends = (OrganizationFilter, TeamFilter)
    org_lookup_field = "organizations"

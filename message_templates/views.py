import re

from django.core.files.base import ContentFile
from django.http import HttpResponse
from rest_framework import mixins, parsers, permissions
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.viewsets import GenericViewSet, ModelViewSet, ReadOnlyModelViewSet

from accounts.permissions import IsOrganizationManager
from cozmo_common.filters import OrganizationFilter
from cozmo_common.pagination import PageNumberFiftyPagination
from . import filters, models, serializers


class IsFromVoyajoy(permissions.BasePermission):
    """Allow sending emails only users with '@voyajoy.com' emails."""

    def has_permission(self, request, view):
        return bool(re.search(r"[.@]voyajoy\.com$", request.user.email))


class DefaultTemplateViewSet(ReadOnlyModelViewSet):

    serializer_class = serializers.DefaultTemplateSerializer
    queryset = models.DefaultTemplate.objects.all()


class MailView(mixins.CreateModelMixin, mixins.ListModelMixin, GenericViewSet):
    """
    post:
    Sends email on behalf of an user.

    Only accepts requests from users, whose email address is from _voyajoy.com_
    domain (or any of its subdomains).

    get:
    Return history of messages in reservations.
    """

    parser_classes = (parsers.FormParser, parsers.MultiPartParser)
    permission_classes = (IsOrganizationManager, IsFromVoyajoy)
    queryset = models.Mail.objects.all().order_by("reservation_id", "date")
    filter_backends = (filters.ReservationFilter,)

    def get_serializer_class(self):
        serializer_class = serializers.MailSerializer

        user = self.request.user
        if user.is_authenticated:
            if user.organization.airbnbapp_set.exists():
                serializer_class = serializers.AirbnbMessageSerializer
            elif user.organization.googleapp_set.exists():
                serializer_class = serializers.GmailSerializer
        return serializer_class

    def perform_create(self, serializer):
        files_data = {"files": self.request.data.getlist("files")}
        files_ser = serializers.FileListSerializer(data=files_data)
        files_ser.is_valid(raise_exception=True)

        serializer.save(attachments=files_ser.validated_data["files"])

    @action(detail=False, methods=["POST"], serializer_class=serializers.RenderSerializer)
    def preview(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        files_data = {"files": self.request.data.getlist("files")}
        files_ser = serializers.FileListSerializer(data=files_data)
        files_ser.is_valid(raise_exception=True)

        serializer.save(attachments=files_ser.validated_data["files"])
        response = HttpResponse(
            ContentFile(serializer.instance.getvalue()), content_type="application/pdf"
        )
        response["Content-Disposition"] = "attachment; filename=email.pdf"
        return response


class TemplateViewSet(ModelViewSet):

    serializer_class = serializers.TemplateSerializer
    queryset = models.Template.objects.all().order_by("id")
    pagination_class = PageNumberFiftyPagination
    filter_backends = (SearchFilter, OrganizationFilter)
    search_fields = ("name", "description")


class TagViewSet(ModelViewSet):

    serializer_class = serializers.TagSerializer
    queryset = models.Tag.objects.all()

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        return queryset.filter(organization__in=(self.request.user.organization, None))


class VariableViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):

    serializer_class = serializers.VariableSerializer
    queryset = models.Variable.objects.all()
    filter_backends = (OrganizationFilter,)


class WelcomeTemplateViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet):

    serializer_class = serializers.WelcomeTemplateSerializer
    queryset = models.WelcomeTemplate.objects.all().order_by("id")
    pagination_class = PageNumberPagination
    filter_backends = (SearchFilter, OrganizationFilter)
    search_fields = ("name", "description")

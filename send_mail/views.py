import json
from logging import getLogger

from django.core.files.base import ContentFile
from django.db.models import Subquery
from django.http import HttpResponse
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.mixins import (
    CreateModelMixin,
    DestroyModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
)
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK
from rest_framework.viewsets import GenericViewSet, ModelViewSet

from accounts.permissions import GroupAccess
from cozmo_common.filters import OrganizationFilter
from cozmo_common.mixins import ApplicationPermissionViewMixin
from cozmo_common.permissions import ApplicationModelPermissions
from listings.filters import GroupAccessFilter
from send_mail.choices import DeliveryStatus, MessageType
from send_mail.models import Conversation, ForwardingEmail
from send_mail.serializers import (
    ConversationSerializer,
    NexmoWebhookSerializer,
    ParseEmailTaskSerializer,
)
from . import filters, models, serializers

logger = getLogger(__name__)


class NexmoWebhookViewset(GenericViewSet):

    permission_classes = (AllowAny,)
    serializer_class = NexmoWebhookSerializer

    def list(self, request, *args, **kwargs):
        """Airbnb Availability webhook"""
        logger.debug("[NEXMO WEBHOOK]: Payload - %s", json.dumps(request.data))
        serializer = self.get_serializer(data=request.query_params)
        logger.debug("[NEXMO WEBHOOK]: Handler - %s", str(serializer))
        if serializer.is_valid():
            serializer.save()
            response = Response(status=HTTP_200_OK)
        else:
            response = Response(status=HTTP_200_OK)
        logger.debug("[NEXMO WEBHOOK]: Response - (%s) %s", HTTP_200_OK, str(response.data))
        return response


class SendgridParseWebhookView(CreateModelMixin, GenericViewSet):

    permission_classes = (AllowAny,)
    parser_classes = (MultiPartParser,)
    serializer_class = ParseEmailTaskSerializer

    def create(self, request, *args, **kwargs):
        """Airbnb Availability webhook"""
        logger.debug("[SENDGRID WEBHOOK]: Payload - %s", request.data)
        data = request.data
        num_files = int(data.get("attachments"))
        attachments = {"files": [data.pop(f"attachment{x}")[0] for x in range(1, num_files + 1)]}

        files_ser = serializers.FileListSerializer(data=attachments)
        files_ser.is_valid(raise_exception=True)
        serializer = self.get_serializer(data={"data": request.data})

        logger.debug("[SENDGRID WEBHOOK]: Handler - %s", str(serializer))
        if serializer.is_valid():
            serializer.save(attachments=files_ser.validated_data.get("files"))
        logger.debug("[SENDGRID WEBHOOK]: Response - (%s)", HTTP_200_OK)
        return Response(status=HTTP_200_OK)


class ConversationView(
    ApplicationModelPermissions,
    RetrieveModelMixin,
    ListModelMixin,
    UpdateModelMixin,
    GenericViewSet,
):
    serializer_class = ConversationSerializer
    permission_classes = (GroupAccess,)
    queryset = Conversation.objects.all().order_by("date_updated")
    filter_backends = (filters.ConversationFilter, GroupAccessFilter, OrganizationFilter)
    group_lookup_field = "reservation__prop__group"
    org_lookup_field = "reservation__prop__organization"

    def get_object_permissions(self, obj):
        return obj.reservation.prop.organization


class MessageViewSet(
    ApplicationModelPermissions,
    RetrieveModelMixin,
    CreateModelMixin,
    ListModelMixin,
    DestroyModelMixin,
    GenericViewSet,
):
    """
    post:
    Sends email on behalf of an user.

    Only accepts requests from users, whose email address is from _voyajoy.com_
    domain (or any of its subdomains).

    get:
    Return history of messages in reservations.
    """

    # parser_classes = (parsers.FormParser, parsers.MultiPartParser)
    queryset = models.Message.objects.all().order_by("conversation_id", "date_created")
    filter_backends = (filters.MessageFilter,)

    def get_object_organization(self, obj):
        return obj.conversation.reservation.prop.organization

    def get_serializer_class(self):
        serializer_class = serializers.MessageSerializer
        user = self.request.user
        if user.is_authenticated:
            message_type = self.request.data.get("type", None)
            if message_type == MessageType.api.name:
                serializer_class = serializers.APIMessageSerializer
            elif (
                message_type == MessageType.email.name and user.organization.googleapp_set.exists()
            ):
                serializer_class = serializers.GmailSerializer
            elif message_type == MessageType.email_managed.name:
                serializer_class = serializers.MailSerializer
            elif message_type == MessageType.sms.name:
                serializer_class = serializers.SMSMessageSerializer
        return serializer_class

    # def perform_create(self, serializer):
    #     files_data = {"files": self.request.data.getlist("files")}
    #     files_ser = serializers.FileListSerializer(data=files_data)
    #     files_ser.is_valid(raise_exception=True)
    #
    #     serializer.save(attachments=files_ser.validated_data["files"])

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


class ConversationInboxViewSet(
    ApplicationModelPermissions,
    RetrieveModelMixin,
    ListModelMixin,
    UpdateModelMixin,
    GenericViewSet,
):
    queryset = models.Message.objects.filter(
        id__in=Subquery(
            models.Message.objects.filter(
                outgoing=False, delivery_status=DeliveryStatus.delivered.value
            )
            .distinct("conversation_id")
            .values("id")
        )
    )

    pagination_class = PageNumberPagination
    serializer_class = serializers.ConversationInboxSerializer
    filter_backends = (OrganizationFilter, GroupAccessFilter, OrderingFilter)
    org_lookup_field = "conversation__reservation__prop__organization"
    group_lookup_field = "conversation__reservation__prop__group"
    ordering = ("-date_created",)


class ForwardingEmailViewSet(ApplicationPermissionViewMixin, ModelViewSet):

    queryset = ForwardingEmail.objects.all()
    serializer_class = serializers.ForwardingEmailSerializer
    filter_backends = (OrganizationFilter,)

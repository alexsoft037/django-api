from functools import partial
from logging import getLogger

from django.http import HttpResponse
from rest_framework.mixins import CreateModelMixin
from rest_framework.parsers import FormParser
from rest_framework.permissions import AllowAny
from rest_framework.viewsets import GenericViewSet, ModelViewSet

from cozmo_common.filters import UserFilter
from .models import Notification, TwilioReply
from .serializers import NotificationSerializer, TwilioReplySerializer

XmlResponse = partial(HttpResponse, content_type="application/xml")
logger = getLogger(__name__)


class NotificationViewSet(ModelViewSet):

    queryset = Notification.objects.filter(is_read=False).order_by("-date_created")
    serializer_class = NotificationSerializer
    filter_backends = (
        UserFilter,
    )
    user_lookup_field = "to"


class TwilioReplyViewSet(CreateModelMixin, GenericViewSet):

    queryset = TwilioReply.objects.all()
    parser_classes = (FormParser,)
    permission_classes = (AllowAny,)
    serializer_class = TwilioReplySerializer
    lookup_data_kwarg = "MessageSid"

    def create(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)
        logger.info("Incomming message from Twilio: %s", request.data)

        if serializer.is_valid():
            self.perform_create(serializer)

        return XmlResponse(serializer.response)

    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        obj = queryset.filter(
            **{self.lookup_field: self.request.data.get(self.lookup_data_kwarg, None)}
        ).first()
        self.check_object_permissions(self.request, obj)
        return obj

import pytz
from django.utils import timezone
from rest_framework.generics import GenericAPIView
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK

from accounts.permissions import GroupAccess
from cozmo_common.fields import AppendFields
from cozmo_common.filters import OrganizationFilter
from dashboard.serializers import DashboardSerializer
from listings.choices import ReservationStatuses
from listings.filters import GroupAccessFilter
from listings.models import Property, Reservation
from send_mail.choices import DeliveryStatus
from send_mail.models import Message
from settings.models import OrganizationSettings

TODO_FIRST_PROPERTY = {
    "title": "Create your first property",
    "url": "/properties/",
    "text": "Take your first step with Cozmo",  # noqa: E501
    "icon": "download",
}
TODO_CHANNEL_NETWORK = {
    "title": "Connect your properties to the channel network",
    "url": "/channelnetwork/",
    "text": "Earn more by exposing your home to multiple rental sites via the rental channel network",  # noqa: E501
    "icon": "channels",
}
TODO_SMART_RESPONSES = {
    "title": "Enable Smart Responses",
    "url": "/settings/responses/",
    "text": "Save more time by enabling our Smart Assistant to respond to simple guest queries",  # noqa: E501
    "icon": "wrench",
}


class DashboardViewSet(RetrieveModelMixin, GenericAPIView):
    # TODO write tests
    permission_classes = (GroupAccess,)
    filter_backends = (OrganizationFilter, GroupAccessFilter)
    serializer_class = DashboardSerializer

    def get_object(self):

        # TODO fix this hardcoded hack
        now = timezone.now()
        t = pytz.timezone("America/Los_Angeles")
        today = now.astimezone(t).date()

        with AppendFields(
            self, {"org_lookup_field": "prop__organization", "group_lookup_field": "prop__group"}
        ):
            arrivals = self.filter_queryset(
                Reservation.objects.filter(start_date=today, status=ReservationStatuses.Accepted)
            )
            departures = self.filter_queryset(
                Reservation.objects.filter(end_date=today, status=ReservationStatuses.Accepted)
            )

        with AppendFields(
            self,
            {
                "org_lookup_field": "conversation__reservation__prop__organization",
                "group_lookup_field": "conversation__reservation__prop__group",
            },
        ):
            messages = self.filter_queryset(
                Message.objects.filter(
                    outgoing=False, delivery_status=DeliveryStatus.delivered.value
                )
                .order_by("conversation_id", "-date_created")
                .distinct("conversation_id")
            )[:5]

        has_properties = self.filter_queryset(Property.objects.all()).exists()

        has_channel_network_enabled = OrganizationSettings.objects.filter(
            channel_network_enabled=True, organization=self.request.user.organization
        ).exists()

        has_smart_responses_enabled = OrganizationSettings.objects.filter(
            chat_settings__enabled=True, organization=self.request.user.organization
        ).exists()

        todo = list()
        if not has_properties:
            todo.append(TODO_FIRST_PROPERTY)
        if not has_channel_network_enabled:
            todo.append(TODO_CHANNEL_NETWORK)
        if not has_smart_responses_enabled:
            todo.append(TODO_SMART_RESPONSES)

        return {
            "bookings": {"arrivals": arrivals, "departures": departures},
            "messages": messages,
            "todo": todo,
        }

    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        return Response(serializer.data, status=HTTP_200_OK)

from django.contrib.contenttypes.models import ContentType
from rest_framework.mixins import ListModelMixin
from rest_framework.viewsets import GenericViewSet
from rest_framework_extensions.mixins import NestedViewSetMixin

from cozmo_common.filters import OrganizationFilter
from listings.models import Reservation
from .models import Event
from .serializers import ReservationEventSerializer


class ReservationEventViewSet(NestedViewSetMixin, ListModelMixin, GenericViewSet):

    serializer_class = ReservationEventSerializer
    filter_backends = (OrganizationFilter,)

    def get_queryset(self):
        return Event.objects.order_by("timestamp").filter(
            content_type=ContentType.objects.get_for_model(Reservation)
        )

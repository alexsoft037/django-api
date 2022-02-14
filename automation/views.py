from rest_framework.viewsets import ModelViewSet

from automation.models import ReservationAutomation
from automation.serializers import ReservationAutomationSerializer


class ReservationAutomationViewSet(ModelViewSet):

    serializer_class = ReservationAutomationSerializer
    queryset = ReservationAutomation.objects.all()

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        return queryset.filter(organization__in=(self.request.user.organization, None))

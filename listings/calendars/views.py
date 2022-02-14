from django.core.files.base import ContentFile
from django.http import HttpResponse
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST
from rest_framework.viewsets import GenericViewSet, ModelViewSet, ReadOnlyModelViewSet
from rest_framework_extensions.mixins import NestedViewSetMixin

from cozmo_common.filters import OrganizationFilter
from listings.filters import PropertyIdFilter
from . import models, serializers
from .filters import TargetFilter


class CalendarViewSet(ReadOnlyModelViewSet):
    """
    Reads Calendars owned by a current user.

    Can be filtered by `prop` using it's id, for example: `/calendars/?prop=10`
    """

    serializer_class = serializers.CalendarSerializer
    queryset = models.CozmoCalendar.objects.all()
    filter_backends = (OrganizationFilter, PropertyIdFilter)
    org_lookup_field = "prop__organization"

    @action(detail=False, methods=["POST"], serializer_class=serializers.CheckCalendarSerializer)
    def check_url(self, request, prop_id=None):
        """Validates URL if it is a valid iCal file."""
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, HTTP_200_OK)

    @action(
        detail=True, methods=["GET"], permission_classes=[AllowAny], filter_backends=[TargetFilter]
    )
    def ical(self, request, pk):
        """Returns iCal file with all events from external calendars."""
        calendar = self.get_object()
        target = request.query_params.get("_target", None)
        if target is None:
            ical = calendar.to_ical()
            ical_name = f"cozmo-{calendar.prop_id}.ics"
        else:
            ical = calendar.to_filtered_ical(calendar_id=target)
            ical_name = f"cozmo-{calendar.prop_id}-{target}.ics"

        response = HttpResponse(ContentFile(ical), content_type="text/calendar; charset=UTF-8")
        response["Content-Disposition"] = f"attachment; filename={ical_name}"
        return response


class ExternalCalendarViewSet(NestedViewSetMixin, ModelViewSet):
    serializer_class = serializers.ExternalCalendarSerializer
    queryset = models.ExternalCalendar.objects.all()

    def perform_create(self, serializer):
        """Create instance based on provieded data plus parent lookup."""
        serializer.save(**self.get_parents_query_dict())

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update(self.get_parents_query_dict())
        return context

    @action(detail=True, methods=["POST"])
    def fetch(self, request, **kwargs):
        cal = self.get_object()
        try:
            cal.fetch(commit=True)
            cal.cozmo_cal.refresh_ical(commit=True)
        except ValueError:
            models.SyncLog.objects.create(calendar=cal, success=False, events=cal.events_count)
            return Response(
                data={"error": "Fetching problem, calendar id={}".format(kwargs.get("pk"))},
                status=HTTP_400_BAD_REQUEST,
            )

        models.SyncLog.objects.create(calendar=cal, success=True, events=cal.events_count)
        cal.refresh_from_db()
        return Response(self.get_serializer(cal).data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        cozmo_cal = instance.cozmo_cal

        destroy_action = super().destroy(request, *args, **kwargs)
        cozmo_cal.refresh_ical(commit=True)
        return destroy_action


class ExternalCalendarEventViewSet(
    mixins.RetrieveModelMixin, mixins.UpdateModelMixin, mixins.ListModelMixin, GenericViewSet
):

    serializer_class = serializers.ExternalCalendarEventSerializer
    queryset = models.ExternalCalendarEvent.objects.all()
    filter_backends = (OrganizationFilter,)
    org_lookup_field = "external_cal__cozmo_cal__prop__organization"


class CalendarColorViewSet(ReadOnlyModelViewSet):

    serializer_class = serializers.CalendarColorSerializer
    queryset = models.CalendarColor.objects.all()

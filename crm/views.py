from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from cozmo_common.filters import OrganizationFilter
from . import filters, models, serializers


class TicketViewSet(viewsets.ModelViewSet):
    """Read, create, update and delete Tickets."""

    queryset = models.Ticket.objects.all().order_by("-date_created", "-priority")
    pagination_class = PageNumberPagination
    filter_backends = (SearchFilter, OrganizationFilter, filters.TicketFilter)
    search_fields = ("id", "title")

    def get_serializer_class(self):
        if self.action == "list":
            serializer_class = serializers.TicketSerializer
        else:
            serializer_class = serializers.TicketDetailedSerializer
        return serializer_class

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization, creator=self.request.user)

    @action(
        detail=False,
        methods=["PATCH"],
        url_path="update",
        get_serializer_class=lambda: serializers.BulkUpdateSerializer,
    )
    def bulk_update(self, request):
        """
        Update multiple Tickets at once.

        Return list of updated tickets.
        """
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(instance.data)

    @action(
        detail=False,
        methods=["PATCH"],
        url_path="archive",
        get_serializer_class=lambda: serializers.BulkArchiveSerializer,
    )
    def bulk_archive(self, request):
        """
        Mark multiple Tickets as archived at once.

        Return list of archived Tickets ids.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.initial_data)

    @action(
        detail=False, methods=["GET"], get_serializer_class=lambda: serializers.StatsSerializer
    )
    def stats(self, request):
        """Read number of Tickets in each pre-defined category."""
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(instance=queryset)
        return Response(serializer.data)

    @action(
        detail=True, methods=["POST"], get_serializer_class=lambda: serializers.MergeSerializer
    )
    def merge(self, request, pk):
        """
        Merge chosen Tickets with parent one.

        This means Messages and Tags will be moved to a parent Ticket and merged tickets
        will be deleted.

        Return updated Ticket.
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance=instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        merged = serializer.save()
        return Response(merged.data)


class MessageViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Create Messages for given Ticket."""

    queryset = models.Message.objects.all()
    serializer_class = serializers.MessageSerializer

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class ContactViewSet(viewsets.ModelViewSet):
    """Read, create update and delete Contacts."""

    queryset = models.Contact.objects.all()
    filter_backends = (OrganizationFilter,)
    serializer_class = serializers.ContactSerializer

    def perform_create(self, serializer):
        serializer.save(organization=self.request.user.organization)

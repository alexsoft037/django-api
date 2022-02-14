from django.contrib.auth import get_user_model
from django.db.models.aggregates import Count
from django.db.models.fields import DateField
from django.db.models.functions import Cast, Lower, TruncDay
from django.http import Http404
from rest_framework import mixins, parsers, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_204_NO_CONTENT
from rest_framework_extensions.mixins import NestedViewSetMixin

from accounts.permissions import GroupAccess, IsVendorOrManager
from accounts.views import UserInviteView
from cozmo_common.filters import MinimalFilter, OrganizationFilter
from cozmo_common.mixins import ApplicationPermissionViewMixin
from cozmo_common.pagination import PageNumberTenPagination
from listings.filters import GroupAccessFilter, PropertyIdFilter
from listings.models import Property
from . import filters, models, serializers

User = get_user_model()


class InstructionViewSet(
    NestedViewSetMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Create, update and delete Instruction information."""

    serializer_class = serializers.InstructionSerializer
    queryset = models.Instruction.objects.all()
    permission_classes = (IsVendorOrManager,)

    def perform_create(self, serializer):
        serializer.save(checklist_item_id=self.get_parents_query_dict()["checklist_item_id"])

    def filter_queryset_by_parents_lookups(self, queryset):
        parents_query_dict = self.get_parents_query_dict()
        if parents_query_dict:
            try:
                parents_query_dict["checklist_item__job_id"] = parents_query_dict.pop("job_id")
                return queryset.filter(**parents_query_dict)
            except ValueError:
                raise Http404
        else:
            return queryset


class JobReportViewSet(ApplicationPermissionViewMixin, viewsets.ModelViewSet):
    parser_classes = (parsers.FormParser, parsers.MultiPartParser)
    serializer_class = serializers.JobReportSerializer
    queryset = models.Report.objects.all()


class JobStatusViewSet(mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = serializers.JobStatusSerializer
    queryset = models.Job.objects.all()
    permission_classes = (IsVendorOrManager,)
    filter_backends = (filters.JobFilter, PropertyIdFilter)

    org_lookup_field = "prop__organization"

    @action(detail=True, methods=["PATCH"], serializer_class=serializers.JobStatusSerializer)
    def status(self, request, pk=None):
        ser = self.get_serializer(data=request.data, prop_id=pk)
        ser.is_valid(raise_exception=True)
        order = ser.save()
        return Response(data=order, status=HTTP_200_OK)


class JobViewSet(ApplicationPermissionViewMixin, viewsets.ModelViewSet):
    """Read, create, update and delete Job information."""

    serializer_class = serializers.JobSerializer
    queryset = models.Job.objects.all().select_related("prop").prefetch_related("checklist")
    pagination_class = PageNumberPagination
    filter_backends = (
        OrganizationFilter,
        filters.JobFilter,
        filters.JobDateFilter,
        PropertyIdFilter,
        GroupAccessFilter,
        OrderingFilter,
        SearchFilter,
    )
    search_fields = (
        "assignee__user__first_name",
        "assignee__user__last_name",
        "assignee__user__email",
        "assignee__user__phone",
        "prop__name",
        "prop__location__address",
        "prop__location__apartment",
        "prop__location__city",
        "prop__location__postal_code",
        "prop__location__state",
    )
    add_permissions = (GroupAccess,)
    org_lookup_field = "prop__organization"
    group_lookup_field = "prop__group"
    ordering_fields = ("date_created",)

    @action(detail=True, methods=["PATCH"], serializer_class=serializers.JobStatusSerializer)
    def status(self, request, pk=None):
        ser = self.get_serializer(data=request.data, prop_id=pk)
        ser.is_valid(raise_exception=True)
        order = ser.save()
        return Response(data=order, status=HTTP_200_OK)


class JobCalendarViewSet(
    ApplicationPermissionViewMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):

    serializer_class = serializers.JobCalendarSerializer
    queryset = (
        models.Job.objects.annotate(date=TruncDay(Cast(Lower("time_frame"), DateField())))
        .values("date", "status")
        .annotate(count=Count("id"))
        .order_by("date")
    )
    permission_classes = (IsVendorOrManager,)
    filter_backends = (OrganizationFilter, filters.JobCalendarFilter)

    org_lookup_field = "prop__organization"


class JobReservationCalView(
    ApplicationPermissionViewMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    serializer_class = serializers.JobReservationSerializer
    queryset = Property.objects.active().with_cleaning_app_enabled().order_by("id")
    filter_backends = (
        OrganizationFilter,
        filters.JobReservationDateFilter,
        SearchFilter,
        GroupAccessFilter,
    )
    add_permissions = (GroupAccess,)
    pagination_class = PageNumberTenPagination
    search_fields = ("name", "location__address", "group__name")


class ChecklistViewSet(NestedViewSetMixin, viewsets.ModelViewSet):
    """
    Read, create, update and delete Checklist information.

    Write operations require `ContentType` set to `multipart/form-data`.
    """

    parser_classes = (parsers.FormParser, parsers.MultiPartParser)
    queryset = models.ChecklistItem.objects.all()
    permission_classes = (IsVendorOrManager,)
    serializer_class = serializers.ChecklistItemSerializer

    def perform_create(self, serializer):
        serializer.save(**self.get_parents_query_dict())


class VendorInviteView(UserInviteView):
    serializer_class = serializers.VendorInviteSerializer
    org_lookup_field = "user__organizations"


class VendorViewSet(ApplicationPermissionViewMixin, viewsets.ModelViewSet):
    """Read and create Vendor profiles."""

    serializer_class = serializers.VendorSerializer
    serializer_class_basic = serializers.VendorMinimalSerializer
    filter_backends = (OrganizationFilter, MinimalFilter)

    org_lookup_field = "user__organizations"

    def get_queryset(self):
        return models.Vendor.objects.all().annotate(jobs_count=Count("job")).select_related("user")

    @action(
        detail=True,
        methods=["PATCH"],
        url_path="jobs/reassign",
        serializer_class=serializers.JobReassingSerializer,
    )
    def reassign(self, request, *args, **kwargs):
        """Reassing all jobs from one Vendor to another."""
        queryset = self.get_object().job_set.all()
        serializer = self.get_serializer(
            queryset, data=[request.data] * queryset.count(), partial=True, many=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(status=HTTP_204_NO_CONTENT)


class AssignmentViewSet(ApplicationPermissionViewMixin, NestedViewSetMixin, viewsets.ModelViewSet):

    serializer_class = serializers.AssignmentSerializer
    queryset = models.Assignment.objects.all().select_related("prop")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update(self.get_parents_query_dict())
        return context

    def perform_create(self, serializer):
        serializer.save(**self.get_parents_query_dict())

    @action(detail=False, methods=["PATCH"], serializer_class=serializers.ReassingSerializer)
    def reassign(self, request, *args, **kwargs):
        """Reassing all Assignments from one Vendor to another."""
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(
            queryset, data=[request.data] * queryset.count(), partial=True, many=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(status=HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["DELETE"])
    def delete(self, request, *args, **kwargs):
        """Reassing all Assignments from one Vendor to another."""
        queryset = self.filter_queryset(self.get_queryset())
        queryset.delete()

        return Response(status=HTTP_204_NO_CONTENT)


class VendorPropertyViewSet(
    ApplicationPermissionViewMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):

    serializer_class = serializers.VendorPropertySerializer
    queryset = Property.objects.active().with_cleaning_app_enabled().order_by("pk")
    filter_backends = (OrganizationFilter, SearchFilter)
    pagination_class = PageNumberTenPagination
    search_fields = ("name", "location__address", "group__name")

    @action(detail=True, methods=["PATCH"], serializer_class=serializers.VendorOrderSerializer)
    def order(self, request, pk=None):
        ser = self.get_serializer(data=request.data, prop_id=pk)
        ser.is_valid(raise_exception=True)
        order = ser.save()
        return Response(data=order, status=HTTP_200_OK)

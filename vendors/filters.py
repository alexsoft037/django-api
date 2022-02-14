from datetime import datetime

from django.db.models.fields import DateField
from django.db.models.functions import Cast, Concat, Lower, TruncDay, TruncMonth
from django.db.models.query import Prefetch
from django.utils import timezone
from rest_framework.compat import coreapi, coreschema
from rest_framework.exceptions import APIException
from rest_framework.filters import BaseFilterBackend

from cozmo_common.filters import DateFilter
from listings.filters import ReservationDateFilter
from .models import Job


class JobFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        filter_kwargs = {
            k: v
            for k, v in {
                "is_active": request.query_params.get("active"),
                "prop__name__icontains": request.query_params.get("name"),
                "full_address__icontains": request.query_params.get("address"),
                "assignee__id": request.query_params.get("assignee"),
                "date": request.query_params.get("date"),
                "prop": request.query_params.get("property"),
            }.items()
            if v is not None
        }

        status_param = request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status__in=status_param.split(","))

        if "full_address__icontains" in filter_kwargs:
            queryset = queryset.annotate(
                full_address=Concat("prop__location__address", "prop__location__apartment")
            )

        if "date" in filter_kwargs:
            try:
                filter_kwargs["date"] = datetime.strptime(filter_kwargs["date"], "%Y-%m-%d").date()
            except ValueError:
                raise APIException('Invalid filter parameter "date"', 400)
            else:
                queryset = queryset.annotate(date=TruncDay(Cast(Lower("time_frame"), DateField())))

        if "property" in filter_kwargs:
            queryset = queryset.filter(prop_id=filter_kwargs["property"])

        if request.user.is_vendor:
            filter_kwargs["assignee__user"] = request.user
        else:
            filter_kwargs["prop__organization"] = request.user.organization

        queryset = queryset.filter(**filter_kwargs)

        # if hasattr(view, "action") and view.action in ["list"]:
        #     start_date = request.query_params.get("startDate") or timezone.now() - timedelta(
        #         days=1
        #     )
        #     end_date = request.query_params.get("endDate")
        #     date_query = {"start_date__gte": start_date}
        #     if end_date:
        #         date_query["start_date__lte"] = end_date
        #     queryset = queryset.filter(**date_query)

        return queryset

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name="active",
                required=False,
                location="query",
                schema=coreschema.Boolean(
                    default="true", description="If a job is active or not."
                ),
            ),
            coreapi.Field(
                name="address",
                required=False,
                location="query",
                schema=coreschema.String(
                    default="104 Example Street", description="Address of a property"
                ),
            ),
            coreapi.Field(
                name="name",
                required=False,
                location="query",
                schema=coreschema.String(
                    default="Awesome property", description="Name of a property"
                ),
            ),
            coreapi.Field(
                name="assignee",
                required=False,
                location="query",
                schema=coreschema.String(
                    default="43123", description="Id of a Vendor assigned to a job"
                ),
            ),
            coreapi.Field(
                name="date",
                required=False,
                location="query",
                schema=coreschema.String(
                    default="2023-12-31", description="Starting day of a job"
                ),
            ),
            coreapi.Field(
                name="property",
                required=False,
                location="query",
                schema=coreschema.String(default="0", description="Property ID"),
            ),
            coreapi.Field(
                name="status",
                required=False,
                location="query",
                schema=coreschema.String(description="Job status"),
            ),
        ]


class JobCalendarFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        now = timezone.now()
        try:
            month = datetime(
                int(request.query_params.get("year", now.year)),
                int(request.query_params.get("month", now.month)),
                1,
            )
        except ValueError:
            raise APIException("Invalid filter parameters", 400)

        return queryset.annotate(
            start_month=TruncMonth(Cast(Lower("time_frame"), DateField()))
        ).filter(start_month=month)

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name="month",
                required=False,
                location="query",
                schema=coreschema.Integer(
                    default=9, description="Number of a month. Defaults to current month."
                ),
            ),
            coreapi.Field(
                name="year",
                required=False,
                location="query",
                schema=coreschema.Integer(
                    default=2024, description="Number of a year. Defaults to current year."
                ),
            ),
        ]


class JobReservationDateFilter(ReservationDateFilter):
    def filter_queryset(self, request, queryset, view):
        queryset = super().filter_queryset(request, queryset, view)
        start, end = self.get_query_params(request)

        return queryset.prefetch_related(
            Prefetch(
                "job_set",
                queryset=Job.objects.annotate(
                    start=TruncDay(Cast(Lower("time_frame"), DateField()))
                ).filter(start__gte=start, start__lte=end),
                to_attr="job_included",
            )
        )


class JobDateFilter(DateFilter):
    def filter_queryset(self, request, queryset, view):
        start, end = self.get_query_params(request)
        action = view.action

        if action == "list":
            return queryset.annotate(
                start=TruncDay(Cast(Lower("time_frame"), DateField()))
            ).filter(start__gte=start, start__lte=end)
        return queryset

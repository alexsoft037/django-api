from contextlib import suppress
from datetime import timedelta

from django.core.exceptions import FieldError
from django.db.models import DateField, Max, Min, Prefetch, Q, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from guardian.shortcuts import get_objects_for_user
from psycopg2.extras import DateRange
from rest_framework.compat import coreapi, coreschema
from rest_framework.exceptions import NotFound, ParseError
from rest_framework.filters import BaseFilterBackend

from cozmo_common.filters import DateFilter
from .choices import PropertyStatuses
from .models import Blocking, Group, Rate, Reservation


class IdFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        prop_id = request.query_params.get("prop")
        if prop_id is not None:
            queryset = queryset.filter(id=prop_id)
            if not queryset.exists():
                raise NotFound("Object with given id does not exist")
        return queryset

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name="prop",
                required=False,
                location="query",
                schema=coreschema.Integer(default=123, description="Id of a property."),
            )
        ]


class MultiReservationFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        guest_id = request.query_params.get("guest")
        if guest_id:
            queryset = queryset.filter(guest_id=guest_id)

        query = request.query_params.get("query")

        if query:
            queryset = queryset.filter(
                Q(guest__first_name__icontains=query)
                | Q(guest__last_name__icontains=query)
                | Q(prop__location__address__icontains=query)
                | Q(prop__name__icontains=query)
            )

        # inq_param = request.query_params.get("inquiry")
        # if inq_param:
        #     inq = json.loads(inq_param)
        #     q = {
        #         "status__in": (
        #             Reservation.Statuses.Inquiry.value,
        #             Reservation.Statuses.Inquiry_Blocked.value,
        #             Reservation.Statuses.Declined.value,
        #             Reservation.Statuses.Request.value,
        #         )
        #     }
        #     queryset = queryset.filter(**q) if inq else queryset.exclude(**q)

        type_param = request.query_params.get("type")
        if type_param:
            inquiry_query = {
                "status__in": (
                    Reservation.Statuses.Inquiry.value,
                    Reservation.Statuses.Inquiry_Blocked.value,
                    Reservation.Statuses.Declined.value,
                    Reservation.Statuses.Request.value,
                )
            }
            if type_param == "inquiries":
                queryset = queryset.filter(**inquiry_query)
            elif type_param == "reservations":
                queryset = queryset.exclude(**inquiry_query)

        status_param = request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status__in=status_param.split(','))

        if hasattr(view, "action") and view.action in ["list", "report"]:
            start_date = request.query_params.get("startDate") or timezone.now() - timedelta(
                days=1
            )
            end_date = request.query_params.get("endDate")
            date_query = {"start_date__gte": start_date}
            if end_date:
                date_query["start_date__lte"] = end_date
            queryset = queryset.filter(**date_query)

        return queryset

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name="guest",
                required=False,
                location="query",
                schema=coreschema.Integer(description="Id of a guest."),
            ),
            coreapi.Field(
                name="query",
                required=False,
                location="query",
                schema=coreschema.String(description="Search field"),
            ),
            coreapi.Field(
                name="inquiry",
                required=False,
                location="query",
                schema=coreschema.Boolean(description="Inquiry only"),
            ),
            coreapi.Field(
                name="startDate",
                required=False,
                location="query",
                schema=coreschema.String(description="Start date"),
            ),
            coreapi.Field(
                name="endDate",
                required=False,
                location="query",
                schema=coreschema.String(description="End date"),
            ),
            coreapi.Field(
                name="status",
                required=False,
                location="query",
                schema=coreschema.String(description="Reservation status"),
            ),
        ]


class PropertyIdFilter(IdFilter):
    def filter_queryset(self, request, queryset, view):
        prop_id = request.query_params.get("prop")
        if prop_id is not None:
            queryset = queryset.filter(prop_id=prop_id)
        return queryset


class ReservationDateFilter(DateFilter):
    def filter_queryset(self, request, queryset, view):
        """Return queryset with Properties which have at least 1 reservation in a given period."""
        start, end = self.get_query_params(request)

        return queryset.prefetch_related(
            Prefetch(
                "reservation_set",
                queryset=Reservation.objects.filter(
                    start_date__contained_by=DateRange(None, end, "[]"),
                    end_date__contained_by=DateRange(start, None, "[]"),
                ),
                to_attr="reservation_included",
            ),
            Prefetch(
                "blocking_set",
                queryset=Blocking.objects.filter(time_frame__overlap=DateRange(start, end, "[]")),
                to_attr="blocking_included",
            ),
            Prefetch(
                "rate_set",
                queryset=Rate.objects.filter(time_frame__overlap=DateRange(start, end, "[]")),
                to_attr="rate_included",
            ),
        ).annotate(
            start_date=Value(start, output_field=DateField()),
            end_date=Value(end, output_field=DateField()),
        )


class OccupancyFilter:
    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name="adults",
                required=False,
                location="query",
                schema=coreschema.Integer(default=1, description="Number of adults"),
            ),
            coreapi.Field(
                name="children",
                required=False,
                location="query",
                schema=coreschema.Integer(default=1, description="Number of children"),
            ),
            coreapi.Field(
                name="pets",
                required=False,
                location="query",
                schema=coreschema.Integer(default=1, description="Number of pets"),
            ),
        ]

    def get_query_params(self, request):
        return {
            name: int(param) if isinstance(param, int) or param.isdigit() else 0
            for name, param in (
                (name, request.query_params.get(name, ""))
                for name in ("adults", "children", "pets")
            )
        }


class CategoryFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        category = request.query_params.get("category")
        if category is not None:
            queryset = queryset.filter(category=category)
        name = request.query_params.get("name")
        if name is not None:
            queryset = queryset.filter(name__istartswith=name)
        return queryset

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name="category",
                required=False,
                location="query",
                schema=coreschema.Integer(default=123, description="Feture category"),
            ),
            coreapi.Field(
                name="name",
                required=False,
                location="query",
                schema=coreschema.String(default="swim", description="Beggining of feature name"),
            ),
        ]


class GroupFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        group_id = request.query_params.get("group")
        if group_id is not None:
            if group_id == "-1":
                group_id = None
            queryset = queryset.filter(group_id=group_id)
        return queryset

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name="group",
                required=False,
                location="query",
                schema=coreschema.Integer(description="Id of a group."),
            )
        ]


class OwnerFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        owner_id = request.query_params.get("owner")
        if owner_id is not None:
            if owner_id == "-1":
                owner_id = None
            queryset = queryset.filter(owner_id=owner_id)
        return queryset

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name="owner",
                required=False,
                location="query",
                schema=coreschema.Integer(description="Id of an owner."),
            )
        ]


class StatusFilter(BaseFilterBackend):
    default_status = PropertyStatuses.Active

    def filter_queryset(self, request, queryset, view):
        status = request.query_params.get("status")
        try:
            queryset = queryset.filter(status=PropertyStatuses[status])
        except KeyError:
            pass
        return queryset

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name="status",
                required=False,
                location="query",
                # schema=coreschema.String(
                #     description=(
                #         "Status of a Property. "
                #         "Defaults to '{}' for list retrieve. "
                #         "Choices are: {}"
                #     ).format(
                #         self.default_status.pretty_name,
                #         ", ".join(s.name for s in PropertyStatuses),
                #     )
                # ),
            )
        ]


class MultiCalendarFilter(ReservationDateFilter):

    MAX_PERIOD = 90

    queries = {
        "bathrooms": (int, "bathrooms"),
        "bedrooms": (int, "bedrooms"),
        "capacity": (int, "max_guests"),
        "features": (list, "features__name__in"),
        "location": (str, "location__city__icontains"),
    }

    def _get_query(self, query_params):
        query = {}
        for f_name, (f_type, f_value) in self.queries.items():
            param = query_params.get(f_name, None)
            if param is None:
                continue

            if f_type is int:
                if not param.isdigit():
                    raise ParseError(f'Invalid value for param "{f_name}"')
                query[f"{f_value}__gte"] = int(param)
            elif f_type is list:
                query[f_value] = param.split(",")
            else:
                query[f_value] = param
        return query

    def filter_queryset(self, request, queryset, view):
        queryset = super().filter_queryset(request, queryset, view)
        query = self._get_query(request.query_params)
        start, end = self.get_query_params(request)
        min_price = request.query_params.get("price_min", None)
        max_price = request.query_params.get("price_max", None)
        if start and end and (min_price or max_price):
            rate_kwargs = {"rate__nightly__lte": max_price, "rate__nightly__gte": min_price}

            query.update(
                {
                    "rate__time_frame__overlap": (start, end),
                    **{k: v for k, v in rate_kwargs.items() if isinstance(v, str) and v.isdigit()},
                }
            )

        order = []
        ordering = request.query_params.get("ordering", "")

        params = ordering.split(" ")
        for p in params:
            if p.find("capacity") != -1:
                max_guests = self.queries["capacity"][1]
                if p.startswith("-"):
                    max_guests = f"-{max_guests}"
                order.append(max_guests)
            if p.find("price") != -1:
                if p.startswith("-"):
                    queryset = queryset.annotate(nightly=Coalesce(Max("rate__nightly"), Value(0)))
                    order.append("-nightly")
                else:
                    queryset = queryset.annotate(
                        nightly=Coalesce(Min("rate__nightly"), Value(100_000_000))
                    )
                    order.append("nightly")
        return queryset.filter(**query).distinct().order_by(*order)

    def get_schema_fields(self, view):
        fields = [
            coreapi.Field(
                name="capacity",
                required=False,
                location="query",
                schema=coreschema.Integer(description="Number of guests allowed."),
            ),
            coreapi.Field(
                name="bedrooms",
                required=False,
                location="query",
                schema=coreschema.Integer(description="Number of bedrooms."),
            ),
            coreapi.Field(
                name="bathrooms",
                required=False,
                location="query",
                schema=coreschema.Integer(description="Number of bathrooms."),
            ),
            coreapi.Field(
                name="features",
                required=False,
                location="query",
                schema=coreschema.Array(description="Featured features."),
            ),
            coreapi.Field(
                name="price_min",
                required=False,
                location="query",
                schema=coreschema.Integer(description="Minimal price per night."),
            ),
            coreapi.Field(
                name="price_max",
                required=False,
                location="query",
                schema=coreschema.Integer(description="Maximal price per night."),
            ),
            coreapi.Field(
                name="location",
                required=False,
                location="query",
                schema=coreschema.String(description="Name of the city."),
            ),
            coreapi.Field(
                name="ordering",
                required=False,
                location="query",
                schema=coreschema.String(description="Order by capacity or price"),
            ),
        ]
        fields.extend(super().get_schema_fields(view))
        return fields


class GroupAccessFilter(BaseFilterBackend):

    default_group_lookup_field = "group"

    def filter_queryset(self, request, queryset, view):
        is_group_contributor = request.user.is_group_contributor
        if not is_group_contributor:
            return queryset

        perms = {"group_access"}
        group_field = getattr(view, "group_lookup_field", self.default_group_lookup_field)
        permitted = get_objects_for_user(
            request.user, perms, Group, with_superuser=False
        ).values_list("id", flat=True)
        query = {f"{group_field}__in": permitted}

        imported_qs = queryset
        with suppress(FieldError):
            imported_qs = queryset.filter(**query)
        return imported_qs if permitted else queryset

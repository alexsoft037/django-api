import json
from datetime import date, datetime, timedelta

from django.utils import timezone
from rest_framework.compat import coreapi, coreschema
from rest_framework.exceptions import NotFound
from rest_framework.fields import BooleanField
from rest_framework.filters import BaseFilterBackend

from accounts.models import OrgMembership


class DateFilter(BaseFilterBackend):

    MAX_PERIOD = 30

    _errors = {
        "invalid_from": 'Invalid "from" date',
        "invalid_range": '"from" after "to"',
        "invalid_to": 'Invalid "to" date',
    }

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name="from",
                required=False,
                location="query",
                schema=coreschema.String(
                    description=("A minimum date included in reservation. Defaults to today."),
                    format=r"\d{4}-\d{2}-\d{2}",
                ),
            ),
            coreapi.Field(
                name="to",
                required=False,
                location="query",
                schema=coreschema.String(
                    description=(
                        "A maximum date included in reservations. "
                        f"Defaults to today + {self.MAX_PERIOD} days."
                    ),
                    format=r"\d{4}-\d{2}-\d{2}",
                ),
            ),
        ]

    def get_query_params(self, request) -> (date, date):
        """Retrieve, normalize and validate filter dates."""
        try:
            raw_start = request.query_params["from"]
            start = datetime.strptime(raw_start, "%Y-%m-%d").date()
        except KeyError:
            start = None
        except ValueError:
            raise NotFound(self._errors["invalid_from"])

        try:
            raw_end = request.query_params["to"]
            end = datetime.strptime(raw_end, "%Y-%m-%d").date()
        except KeyError:
            end = None
        except ValueError:
            raise NotFound(self._errors["invalid_to"])

        start, end = self._normalize_dates(start, end)
        self._validate_dates(start, end)

        return start, end

    def _normalize_dates(self, start, end):
        if start is None and end is None:
            start = timezone.now().date()
            end = start + timedelta(days=self.MAX_PERIOD)
        elif start and end is None:
            end = start + timedelta(days=self.MAX_PERIOD)
        elif end and start is None:
            start = end - timedelta(days=self.MAX_PERIOD)

        return start, end

    def _validate_dates(self, start, end):
        period = (end - start).days
        if period < 0:
            raise NotFound(self._errors["invalid_range"])

        return start, end


class MinimalFilter(BaseFilterBackend):
    """
    Allow user to choose less detiled serializer.

    Expects that a view using this filter will have `serializer_class_basic` attribute.
    """

    def filter_queryset(self, request, queryset, view):
        use_basic = json.loads(request.query_params.get("basic", "false"))
        if use_basic:
            view.serializer_class = type(view).serializer_class_basic
        return queryset

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name="basic",
                required=False,
                location="query",
                schema=coreschema.Boolean(default="true", description="Minimal response data"),
            )
        ]


class OrganizationFilter(BaseFilterBackend):

    default_org_lookup_field = "organization"

    def filter_queryset(self, request, queryset, view):
        organization = request.user.organization
        if organization:
            org_field = getattr(view, "org_lookup_field", self.default_org_lookup_field)
            queryset = queryset.filter(**{org_field: organization})
        else:
            queryset = queryset.none()
        return queryset


class UserFilter(BaseFilterBackend):

    default_user_lookup_field = "user"

    def filter_queryset(self, request, queryset, view):
        user = request.user
        if user:
            user_field = getattr(view, "user_lookup_field", self.default_user_lookup_field)
            queryset = queryset.filter(**{user_field: user})
        else:
            queryset = queryset.none()
        return queryset


class OrgGroupFilter(BaseFilterBackend):

    default_org_lookup_field = "organization"

    def filter_queryset(self, request, queryset, view):
        organization = request.user.organization
        if organization:
            org_field = "{}__in".format(
                getattr(view, "org_lookup_field", self.default_org_lookup_field))
            child_orgs = [o.child for o in OrgMembership.objects.filter(parent=organization)]
            queryset = queryset.filter(**{org_field: [organization] + child_orgs})
        elif request.user.is_superuser:
            return queryset
        else:
            queryset = queryset.none()
        return queryset


class CouponValidFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        if request.query_params.get("is_valid") is not None:
            return queryset.filter(
                is_valid=BooleanField().to_internal_value(request.query_params["is_valid"])
            )
        return queryset

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name="is_valid",
                required=False,
                location="query",
                schema=coreschema.Boolean(default="true", description="Valid coupons"),
            )
        ]

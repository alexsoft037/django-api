from rest_framework.compat import coreapi, coreschema
from rest_framework.filters import BaseFilterBackend


class NumberSearchFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        return queryset.none()

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name="country_code",
                required=True,
                location="query",
                schema=coreschema.String(description="ISO-3166 format country code (i.e. \"US\")")
            ),
            coreapi.Field(
                name="capabilities",
                required=False,
                location="query",
                schema=coreschema.String(description="Comma-delimited functions (i.e. SMS, VOICE"),
            ),
            coreapi.Field(
                name="phone_type",
                required=False,
                location="query",
                schema=coreschema.String(description="Phone type (i.e. landline, mobile"),
            ),
            coreapi.Field(
                name="pattern",
                required=False,
                location="query",
                schema=coreschema.String(description="Search string that starts with {pattern}"),
            ),
        ]

from rest_framework.compat import coreapi, coreschema
from rest_framework.filters import BaseFilterBackend


class TargetFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        return queryset

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name="_target",
                required=False,
                location="query",
                schema=coreschema.Integer(default=0, description="Id of an external calendar."),
            )
        ]

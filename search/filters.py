from rest_framework.compat import coreapi, coreschema
from rest_framework.filters import BaseFilterBackend


class GenericSearchFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        return queryset

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name="q",
                required=False,
                location="query",
                schema=coreschema.String(
                    title="Custom filter string",
                    description=(
                        "It does filtration of Properties, Reservations,"
                        "Conversation Threads and Contacts"
                    ),
                ),
            )
        ]

from rest_framework.compat import coreapi, coreschema
from rest_framework.filters import BaseFilterBackend


class ReservationFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        if "reservation" in request.query_params:
            queryset = queryset.filter(reservation_id=request.query_params["reservation"])

        return queryset

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name="reservation",
                required=False,
                location="query",
                schema=coreschema.Integer(
                    title="Id of a Reservation", description="Id of a Reservation", default="43123"
                ),
            )
        ]

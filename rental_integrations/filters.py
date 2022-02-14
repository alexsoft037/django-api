from rest_framework.compat import coreapi, coreschema
from rest_framework.filters import BaseFilterBackend

from rental_integrations.airbnb.models import AirbnbSync
from rental_integrations.trip_advisor.models import TripAdvisorSync


class ChannelFilter(BaseFilterBackend):
    channel_param = "channel"

    channels = dict(airbnb=0, bookingcom=1, tripadvisor=2, homeaway=3)

    channel_models = dict(airbnb=AirbnbSync, tripadvisor=TripAdvisorSync)

    def filter_queryset(self, request, queryset, view):
        channel = request.query_params.get(self.channel_param, "").lower()
        head, sep, tail = channel.partition("-")
        if channel:
            props = self.channel_models[head or tail].objects.values_list("prop", flat=True)
            if sep:
                queryset = queryset.exclude(pk__in=props)
            else:
                queryset = queryset.filter(pk__in=props)
        return queryset

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name=self.channel_param,
                required=False,
                location="query",
                schema=coreschema.String(
                    description=(
                        "Name of Channel where Properties are exported. "
                        "Prefix with `-` for not exported Properties."
                    )
                ),
            )
        ]

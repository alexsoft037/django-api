from collections import OrderedDict

from django.core.exceptions import ObjectDoesNotExist, ValidationError, MultipleObjectsReturned
from django.utils import timezone
#from djangorestframework_camel_case.parser import CamelCaseJSONParser
#from djangorestframework_camel_case.render import CamelCaseJSONRenderer
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST
from rest_framework.versioning import URLPathVersioning
from rest_framework.viewsets import GenericViewSet
from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_tracking.mixins import LoggingMixin

from accounts.permissions import HasPublicApiAccess, IsPublicApiUser
from cozmo_common.filters import OrgGroupFilter, OrganizationFilter
from listings import filters, models, services, views
from listings.choices import Currencies
from public_api.filters import (
    AllowedStatusFilter,
    FormatFilter,
    GroupFilter,
    LegacyIdFilter,
    PublicApiAccessFilter,
)
from . import serializers, throttling


class ApiVersioning(URLPathVersioning):
    default_version = "v1"
    allowed_versions = ("v1",)


class BaseAPIViewSet(LoggingMixin):
    permission_classes = (IsPublicApiUser,)
    versioning_class = ApiVersioning
#    parser_classes = (CamelCaseJSONParser,)
#    renderer_classes = (CamelCaseJSONRenderer,)
    throttle_classes = (throttling.BurstRateThrottle, throttling.SustainedRateThrottle)

    def should_log(self, request, response):
        """Log only errors"""
        return response.status_code >= 500


class PropertyViewSet(
    BaseAPIViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet
):

    permission_classes = (HasPublicApiAccess,)
    queryset = models.Property.objects.all().order_by("id")
    filter_backends = [
        FormatFilter,
        LegacyIdFilter,
        OrgGroupFilter,
        GroupFilter,
        PublicApiAccessFilter,
        AllowedStatusFilter,
    ]

    def get_queryset(self):
        queryset = super().get_queryset().existing()
        if self.action == "retrieve":
            queryset = queryset.select_related(
                "location", "basic_amenities", "booking_settings", "descriptions"
            ).prefetch_related("image_set", "features")
        return queryset

    def get_serializer_class(self):
        """Chooses serializer depending on action type."""
        serializer_class = serializers.PropertySerializer
        if self.action == "list":
            serializer_class = serializers.RentalMinimalSerializer
        return serializer_class

    @action(detail=True, methods=["GET"])
    def blockings(self, request, pk):
        prop = self.get_object()
        start_date, end_date = filters.DateFilter().get_query_params(self.request)

        ipa = services.IsPropertyAvailable(prop, start_date, end_date)
        ipa.run_check()

        return Response({"date_updated": ipa.latest, "data": ipa.blocked_days})

    @action(
        detail=True,
        methods=["GET"],
        get_serializer_class=lambda: serializers.AvailabilityCalendarSerializer,
    )
    def availability_calendar(self, request, pk):
        prop = self.get_object()
        serializer = self.get_serializer(prop)
        return Response(serializer.data)


class ApiListMixin:
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        serializer = self.get_serializer(queryset, many=True)

        try:
            latest = queryset.values_list("date_updated", flat=True).latest("date_updated")
        except ObjectDoesNotExist:
            latest = timezone.now()

        return Response(OrderedDict([("date_updated", latest), ("data", serializer.data)]))


class StayRequirementsViewSet(
    BaseAPIViewSet, NestedViewSetMixin, ApiListMixin, mixins.RetrieveModelMixin, GenericViewSet
):
    """Read Rate StayRequirements information of a properties."""

    queryset = models.Availability.objects.all()
    serializer_class = serializers.StayRequirementsSerializer
    filter_backends = (OrganizationFilter,)
    org_lookup_field = "prop__organization"

    def get_queryset(self):
        return super().get_queryset().order_by("time_frame")


class QuoteViewSet(BaseAPIViewSet, views.QuoteViewSet):
    """Property Quote."""

    always_include_quote = False

    def _get_rate_serializer(self):
        return serializers.ReservationRateSerializer

    def _get_fee_serializer(self):
        return serializers.ReservationFeeSerializer

    def _get_discount_serializer(self):
        return serializers.ReservationDiscountSerializer

    def _get_quote_response(self, prop, dates):
        reservation = models.Reservation(start_date=dates[0], end_date=dates[1], prop=prop)

        reservation.calculate_price(commit=False)

        visit_rates = models.Rate.visit_rates(dates[0], dates[1], prop.id)
        reservation_rate = self._get_reservation_rate(visit_rates, reservation)
        sum_rates = reservation_rate.value
        reservation.base_total = sum_rates
        reservation_fees = self._get_reservation_fees(reservation, sum_rates)
        reservation_discounts = self._get_discounts(
            prop, reservation.days_to_stay, sum_rates, reservation
        )

        currency = getattr(prop.pricing_settings, "currency", Currencies.USD.pretty_name)
        price = reservation.price
        return {
            "currency": currency,
            "total_price": price,
            "total_price_formatted": "{0}{1}".format(
                Currencies[currency].symbol, price
            ),
            "rate": {
                "amount": str(reservation.base_total),
                "amountFormatted": f"${reservation.base_total}",
                "duration": reservation.nights
            },
            "nightly_price": str(reservation.nightly_price),
            "base_total": str(reservation.base_total),
            "fees": self._get_fee_serializer()(reservation_fees, many=True).data,
            "discounts": self._get_discount_serializer()(
                reservation_discounts, many=True
            ).data,
        }


class AvailabilityViewSet(QuoteViewSet):
    """Property Quote."""

    def list(self, request, prop_id):
        dates = filters.DateFilter().get_query_params(self.request)
        occupancy = filters.OccupancyFilter().get_query_params(request)
        try:
            prop = self._get_property(request)
        except ValidationError:
            return Response(
                data={"error": "invalid value for prop query param"}, status=HTTP_400_BAD_REQUEST
            )
        except MultipleObjectsReturned:
            return Response(
                data={"error": "prop query param is required"}, status=HTTP_400_BAD_REQUEST
            )

        ipa = services.IsPropertyAvailable(prop, dates[0], dates[1], should_sync=True)
        ipa.run_check()
        available = ipa.is_available()

        response_data = {
            **occupancy,
            "available": available,
            "arrival_date": dates[0],
            "departure_date": dates[1],
            "nights": (dates[1] - dates[0]).days,
        }

        return Response(response_data)


class ReservationViewSet(
    BaseAPIViewSet, mixins.CreateModelMixin, mixins.RetrieveModelMixin, GenericViewSet
):
    """Create and Read Reservations"""

    queryset = models.Reservation.objects.all()
    filter_backends = (OrganizationFilter,)
    serializer_class = serializers.ReservationSerializer
    org_lookup_field = "prop__organization"
    lookup_url_kwarg = "confirmation_code"
    lookup_field = "confirmation_code"

    def get_queryset(self):
        return super().get_queryset().order_by("-end_date", "id")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["organization"] = self.request.user.organization
        return ctx

    @action(detail=True, methods=["PATCH"], url_path="cancellation")
    def cancel(self, request, confirmation_code):
        reservation = self.get_object()
        data = {"status": models.Reservation.Statuses.Cancelled.name}

        serializer = self.get_serializer(instance=reservation, data=data, partial=True)

        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(data=serializer.data)


class RateViewSet(BaseAPIViewSet, NestedViewSetMixin, ApiListMixin, GenericViewSet):
    """Property Rates"""

    queryset = models.Rate.objects.all()
    filter_backends = (OrganizationFilter,)
    serializer_class = serializers.RateSerializer
    org_lookup_field = "prop__organization"

    def get_queryset(self):
        return super().get_queryset().order_by("id")


class FeeViewSet(BaseAPIViewSet, NestedViewSetMixin, ApiListMixin, GenericViewSet):
    """Property Fees"""

    queryset = models.AdditionalFee.objects.all()
    filter_backends = (OrganizationFilter,)
    serializer_class = serializers.FeeSerializer
    org_lookup_field = "prop__organization"

    def get_queryset(self):
        return super().get_queryset().order_by("id")

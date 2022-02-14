import csv
from collections import namedtuple
from decimal import Decimal
from functools import wraps
from itertools import chain

from django.core import exceptions
from django.core.cache import cache
from django.db.models import F, Sum, Value
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics, mixins, parsers, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_422_UNPROCESSABLE_ENTITY,
)
from rest_framework_extensions.mixins import NestedViewSetMixin

from accounts.permissions import GroupAccess
from cozmo_common.filters import MinimalFilter, OrganizationFilter
from cozmo_common.mixins import ApplicationPermissionViewMixin
from listings.filters import GroupAccessFilter
from listings.models import GroupUserAssignment, ExternalListing
from rental_integrations.filters import ChannelFilter
from . import filters, models, serializers, services
from .choices import Currencies


def cache_result(cache_key, cache_for):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            value = cache.get(cache_key, None)
            if value is None:
                value = func(*args, **kwargs)
                cache.set(cache_key, value, cache_for)
            return value

        return wrapper

    return decorator


class NestedCreateMixin:
    """Add parent lookup data while saving nested object."""

    def initialize_parent(self, request):
        raise NotImplementedError

    def perform_create(self, serializer):
        """Create instance based on provieded data plus parent lookup."""
        serializer.save(**self.get_parents_query_dict())

    def create(self, request, *args, **kwargs):
        # Ensure Property exists and request.user has permissions to write to it
        self.initialize_parent(request)
        return super().create(request, *args, **kwargs)


class NestedPropertyCreateMixin(NestedCreateMixin):
    def initialize_parent(self, request):
        pk = self.get_parents_query_dict()["prop_id"]
        view = PropertyViewSet(
            request=request, kwargs={PropertyViewSet.lookup_field: pk}, action="retrieve"
        )
        view.get_object()


class NestedReservationCreateMixin(NestedCreateMixin):
    def initialize_parent(self, request):
        pk = self.get_parents_query_dict()["reservation_id"]
        view = ReservationViewSet(request=request, kwargs={ReservationViewSet.lookup_field: pk})
        view.get_object()


class ChargeView(generics.ListAPIView):

    queryset = models.Property.objects.existing().order_by("id")
    filter_backends = (OrganizationFilter, filters.IdFilter)
    serializer_class = serializers.ChargeSerializer
    charge_class = namedtuple("Charge", ["discounts", "fees", "rates", "taxes", "prop"])

    def _get_charge(self, prop_id):
        return self.get_serializer(
            instance=self.charge_class(
                discounts=models.Discount.objects.filter(prop_id=prop_id),
                fees=models.AdditionalFee.objects.fees().filter(prop_id=prop_id),
                rates=models.Rate.objects.filter(prop_id=prop_id),
                taxes=models.AdditionalFee.objects.taxes().filter(prop_id=prop_id),
                prop=prop_id,
            )
        ).data

    def list(self, request):
        """Read all charge information at once."""
        queryset = self.get_queryset()
        queryset = self.filter_queryset(queryset)
        data = (self._get_charge(values["id"]) for values in queryset.values("id"))
        return Response(data, HTTP_200_OK)


class DiscountViewSet(viewsets.ModelViewSet):
    """Read, create, update and delete Discount information for a concrete property."""

    queryset = models.Discount.objects.all()
    serializer_class = serializers.DiscountSerializer
    filter_backends = (filters.PropertyIdFilter, OrganizationFilter)
    org_lookup_field = "prop__organization"


class FeeViewSet(viewsets.ModelViewSet):
    """Read, create, update and delete Fee information for a concrete property."""

    queryset = models.AdditionalFee.objects.fees().all()
    serializer_class = serializers.FeeSerializer
    filter_backends = (filters.PropertyIdFilter, OrganizationFilter)
    org_lookup_field = "prop__organization"


class NestedFileViewSet(NestedPropertyCreateMixin, NestedViewSetMixin, viewsets.ModelViewSet):
    """Read, create, update and delete File information."""

    serializer_order_class = None

    def get_serializer_class(self):
        if self.action == "order":
            if self.serializer_order_class is None:
                raise ValueError("Missing serializer_order_class")
            return self.serializer_order_class
        return super().get_serializer_class()

    @action(detail=False, methods=["POST"], parser_classes=[parsers.JSONParser])
    def order(self, request, prop_id=None):
        """
        Change display order of files.

        Requires a sorted list of all files belonging to a current property.
        """
        ser = self.get_serializer(data=request.data, prop_id=prop_id)
        ser.is_valid(raise_exception=True)
        order = ser.save()
        return Response(data=order, status=HTTP_200_OK)


class ImageViewSet(NestedFileViewSet):
    """Read, create, update and delete Image information."""

    parser_classes = (parsers.FormParser, parsers.MultiPartParser)
    serializer_class = serializers.ImageSerializer
    serializer_order_class = serializers.ImageOrderSerializer
    queryset = models.Image.objects.all()


class VideoViewSet(NestedFileViewSet):
    """Read, create, update and delete Video information."""

    parser_classes = (parsers.FormParser, parsers.MultiPartParser)
    serializer_class = serializers.VideoSerializer
    serializer_order_class = serializers.VideoOrderSerializer
    queryset = models.Video.objects.all()


class PointOfInterestViewSet(NestedPropertyCreateMixin, NestedViewSetMixin, viewsets.ModelViewSet):
    """Read, create, update and delete PointOfInterestViewSet information."""

    serializer_class = serializers.PointOfInterestSerializer
    queryset = models.PointOfInterest.objects.all()

    def get_serializer(self, *args, **kwargs):
        if self.action == "create":
            kwargs["many"] = isinstance(kwargs.get("data", None), list)
        return super().get_serializer(*args, **kwargs)

    @action(
        detail=False,
        methods=["DELETE"],
        serializer_class=serializers.RoomSerializer,
        url_path="bulk",
    )
    def bulk_delete(self, request, prop_id=None):
        """Delete multiple POIS"""
        self.filter_queryset(self.get_queryset()).delete()

        return Response(status=HTTP_204_NO_CONTENT)


class PropertyViewSet(ApplicationPermissionViewMixin, NestedViewSetMixin, viewsets.ModelViewSet):
    """Read, create, update and delete Property information."""

    # .annotate(
    #     first_image=Subquery(
    #         Image.objects.filter(
    #             prop=OuterRef("pk"),
    #             order=0
    #         ).values("url")[:1]
    #     ),
    #     first_thumbnail=Subquery(
    #         Image.objects.filter(
    #             prop=OuterRef("pk"),
    #             order=0
    #         ).values("thumbnail")[:1]
    #     )
    # )

    queryset = (
        models.Property.objects.prefetch_related("image_set")
        .select_related(
            "location",
            "descriptions",
            "pricing_settings",
            "booking_settings",
            "basic_amenities",
            "suitability",
        )
        .existing()
        .order_by("-id")
    )
    filter_backends = (
        OrganizationFilter,
        filters.GroupFilter,
        filters.StatusFilter,
        filters.OwnerFilter,
        MinimalFilter,
        SearchFilter,
        ChannelFilter,
        GroupAccessFilter,
    )
    search_fields = (
        "name",
        "location__address",
        "location__apartment",
        "location__city",
        "location__postal_code",
        "location__state",
        "owner__user__first_name",
        "owner__user__last_name",
    )
    pagination_class = PageNumberPagination
    serializer_class = serializers.PropertySerializer
    serializer_class_basic = serializers.PropertyMinimalSerializer

    @property
    def paginator(self):
        if self.serializer_class == self.serializer_class_basic:
            self._paginator = None
        else:
            self._paginator = super().paginator
        return self._paginator

    # def get_serializer(self, *args, **kwargs):
    #     serializer_class = self.get_serializer_class()
    #     kwargs["context"] = self.get_serializer_context()
    #     if issubclass(serializer_class, serializers.ReservationSerializer):
    #         kwargs["skip_ipa_validation"] = True
    #     return serializer_class(*args, **kwargs)

    def get_serializer(self, *args, **kwargs):
        kwargs["context"] = self.get_serializer_context()
        return super().get_serializer(*args, **kwargs, extra_required=("location", "name"))

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["organization"] = self.request.user.organization
        return ctx

    def get_queryset(self):
        return {
            # "partial_update": self.queryset.list(),
            # "update": serializers.PropertyCreateSerializer,
            # "create": serializers.PropertyCreateSerializer,
            "list": self.queryset.list()
        }.get(self.action, self.queryset)

    def get_serializer_class(self):
        """Chooses serializer depending on action type."""
        serializer_class = self.serializer_class
        if serializer_class is not self.serializer_class_basic:
            serializer_class = {
                "partial_update": serializers.PropertyUpdateSerializer,
                "update": serializers.PropertyCreateSerializer,
                "create": serializers.PropertyCreateSerializer,
                "list": serializers.PropertyListSerializer,
            }.get(self.action, self.serializer_class)
        return serializer_class

    def update(self, request, *args, **kwargs):
        """Update Property information."""
        super().update(request, *args, **kwargs)
        serializer = serializers.PropertyCreateSerializer(
            self.get_object(), data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid()
        return Response(data=serializer.data)

    def perform_destroy(self, instance):
        instance.request_user = self.request.user
        super().perform_destroy(instance)


class RateViewSet(viewsets.ModelViewSet):
    """Read, create, update and delete Rate information of a properties."""

    queryset = models.Rate.objects.order_by("time_frame")
    serializer_class = serializers.RateSerializer
    filter_backends = (OrganizationFilter, filters.PropertyIdFilter)
    org_lookup_field = "prop__organization"


class AvailabilityViewSet(NestedPropertyCreateMixin, NestedViewSetMixin, viewsets.ModelViewSet):
    """Read, create, update and delete Rate information of a properties."""

    queryset = models.Availability.objects.order_by("time_frame")
    serializer_class = serializers.AvailabilitySerializer
    filter_backends = (OrganizationFilter,)
    org_lookup_field = "prop__organization"


class ReservationViewSet(ApplicationPermissionViewMixin, viewsets.ModelViewSet):
    """Read, create, update and delete Reservation information."""

    queryset = (
        models.Reservation.objects.prefetch_related(
            "reservationfee_set", "reservationdiscount_set", "payments"
        )
        .select_related("prop", "guest", "conversation")
        .all()
        .order_by("id")
    )
    serializer_class = serializers.ReservationSerializer
    pagination_class = PageNumberPagination
    filter_backends = (
        OrganizationFilter,
        filters.MultiReservationFilter,
        OrderingFilter,
        SearchFilter,
        GroupAccessFilter,
    )
    search_fields = (
        "confirmation_code",
        "guest__first_name",
        "guest__last_name",
        "guest__email",
        "guest__phone",
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
    ordering_fields = ("start_date", "date_created")

    def get_serializer(self, *args, **kwargs):
        serializer_class = self.get_serializer_class()
        kwargs["context"] = self.get_serializer_context()
        if issubclass(serializer_class, serializers.ReservationSerializer):
            kwargs["skip_ipa_validation"] = True
        return serializer_class(*args, **kwargs)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["organization"] = self.request.user.organization
        return ctx

    def perform_destroy(self, instance):
        instance.request_user = self.request.user
        super().perform_destroy(instance)

    @action(
        detail=False,
        methods=["GET"],
        get_serializer_class=lambda: serializers.ReservationReportSerializer,
    )
    def report(self, request):
        """Return CSV of reservations"""
        queryset = self.get_queryset()
        queryset = self.filter_queryset(queryset)
        serializer = self.get_serializer(many=True, instance=queryset)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="reservations.csv"'

        fieldnames = self.get_serializer_class().Meta.fields

        writer = csv.DictWriter(response, fieldnames)
        writer.writeheader()

        for row in serializer.data:
            writer.writerow(row)

        return response

    # Need to override get_serializer_class, otherwise decorator won't override serializer
    # XXX COZ-557 Remove after front end adapts
    @action(
        detail=True, methods=["PATCH"], get_serializer_class=lambda: serializers.GuestSerializer
    )
    def guest(self, request, pk):
        reservation = self.get_object()

        try:
            serializer = self.get_serializer(
                instance=reservation.guest, data=request.data, partial=True
            )
        except exceptions.ObjectDoesNotExist:
            raise Http404

        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(data=serializer.data)

    @action(
        detail=True, methods=["PATCH"], get_serializer_class=lambda: serializers.InquirySerializer
    )
    def send_inquiry(self, request, pk):
        reservation = self.get_object()

        # To not modify reservations which are not inquiry
        if not reservation.is_inquiry:
            raise Http404

        serializer = self.get_serializer(instance=reservation, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response()


class ReservationCalendarView(
    mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = models.Property.objects.all().order_by("pk")
    serializer_class = serializers.PropertyCalSerializer
    pagination_class = PageNumberPagination
    filter_backends = (
        SearchFilter,
        filters.MultiCalendarFilter,
        OrganizationFilter,
        GroupAccessFilter,
    )
    search_fields = ("name", "location__address")


class RoomViewSet(NestedPropertyCreateMixin, NestedViewSetMixin, viewsets.ModelViewSet):
    """Read, create, update and delete Room information."""

    serializer_class = serializers.RoomSerializer
    queryset = models.Room.objects.all()

    @action(
        detail=False, methods=["PUT"], serializer_class=serializers.RoomSerializer, url_path="bulk"
    )
    def bulk_update(self, request, prop_id=None):
        """Create many rooms at once. Accepts list of room data."""
        ser = self.get_serializer(data=request.data, many=True)
        ser.is_valid(raise_exception=True)
        models.Room.objects.filter(prop_id=prop_id).delete()
        instances = ser.save(prop_id=prop_id)
        data = (serializers.RoomSerializer(i).data for i in instances)
        return Response(data=data, status=HTTP_201_CREATED)


class TaxViewSet(viewsets.ModelViewSet):
    """Read, create, update and delete Tax information for a concrete property."""

    queryset = models.AdditionalFee.objects.taxes().all()
    serializer_class = serializers.TaxSerializer
    filter_backends = (filters.PropertyIdFilter, OrganizationFilter)
    org_lookup_field = "prop__organization"


class GroupViewSet(ApplicationPermissionViewMixin, viewsets.ModelViewSet):
    """Read, create, update and delete Group information."""

    queryset = models.Group.objects.all()
    serializer_class = serializers.GroupSerializer

    @action(detail=True, methods=["PUT"])
    def assign_properties(self, request, pk):
        """Assign Properties to group"""
        group = self.get_object()

        queryset = OrganizationFilter().filter_queryset(
            request, models.Property.objects.existing(), self
        )
        properties = queryset.filter(id__in=request.data)

        return Response({"assigned": properties.update(group=group)})


class QuoteViewSet(NestedViewSetMixin, viewsets.ViewSet):
    """Retrieve Quote"""

    queryset = models.Property.objects.existing().order_by("id")
    # filter_backend are only to display in swagger
    filter_backends = (filters.DateFilter, filters.OccupancyFilter)
    always_include_quote = True

    def _get_property(self, request):
        queryset = OrganizationFilter().filter_queryset(request, self.queryset, self)
        pk = queryset.model._meta.pk.to_python(self.get_parents_query_dict()["prop_id"])
        return get_object_or_404(queryset, pk=pk)

    def _get_reservation_fees(self, reservation, sum_rates):
        # Fees
        fees_with_taxes = reservation.prop.fees_with_taxes().fixed_case(
            reservation.days_to_stay, reservation.guests
        )

        sum_fees = fees_with_taxes.aggregate(total=Sum("partial_value"))["total"] or 0

        # Per_Stay_Only_Rates_Percent amount / 100 * sum_rates
        rate_percent_fees = reservation.prop.per_stay_only_rates_percent_fee().annotate(
            partial_value=F("value") / Decimal("100") * Value(sum_rates)
        )

        # Per_Stay_Percent amount / 100 * (sum_rates + sum_fees)
        stay_percent = reservation.prop.per_stay_percent_fee().annotate(
            partial_value=F("value") / Decimal("100") * Value(sum_rates + sum_fees)
        )

        # Per_Stay_No_Taxes_Percent
        sum_no_tax_fees = (
            reservation.prop.fees_without_taxes()
            .fixed_case(reservation.days_to_stay, reservation.guests)
            .aggregate(total=Sum("partial_value"))["total"]
            or 0
        )

        no_tax_percent_fees = reservation.prop.per_stay_no_taxe_percent_fees().annotate(
            partial_value=F("value") / Decimal("100") * Value(sum_rates + sum_no_tax_fees)
        )

        return [
            models.ReservationFee(
                name=fee.name,
                value=fee.partial_value,
                fee_tax_type=fee.fee_tax_type,
                refundable=fee.refundable,
                optional=fee.optional,
                taxable=fee.taxable,
                reservation=reservation,
            )
            for fee in chain(no_tax_percent_fees, stay_percent, rate_percent_fees, fees_with_taxes)
        ]

    def _get_reservation_rate(self, visit_rates, reservation):
        sum_rates = sum(duration * rate.nightly for rate, duration in visit_rates.items())
        sum_days = sum(visit_rates.values())
        return models.ReservationRate(value=sum_rates, duration=sum_days, reservation=reservation)

    def _get_discounts(self, prop, days_to_stay, sum_rates, reservation):
        discounts = models.Discount.objects.filter(prop=prop)

        disc_percent = discounts.filter(is_percentage=True).annotate(
            partial_value=F("value") / Decimal("100") * Value(sum_rates)
        )
        disc_fixed = discounts.filter(is_percentage=False).fixed_case(days_to_stay)

        reservation_discounts = [
            models.ReservationDiscount(
                value=discount.partial_value,
                discount_type=discount.discount_type,
                optional=discount.optional,
                reservation=reservation,
            )
            for discount in disc_percent
        ]

        reservation_discounts += [
            models.ReservationDiscount(
                value=discount.partial_value,
                discount_type=discount.discount_type,
                optional=discount.optional,
                reservation=reservation,
            )
            for discount in disc_fixed
        ]

        return reservation_discounts

    def _get_rate_serializer(self):
        return serializers.ReservationRateSerializer

    def _get_fee_serializer(self):
        return serializers.ReservationFeeSerializer

    def _get_discount_serializer(self):
        return serializers.ReservationDiscountSerializer

    def _get_availability_response(self, prop, occupancy, dates):
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
        return response_data

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
            "price": str(price),
            "price_formatted": "{0}{1}".format(Currencies[currency].symbol, price),
            "nightly_price": str(reservation.nightly_price),
            "base_total": str(reservation.base_total),
            "fees": self._get_fee_serializer()(reservation_fees, many=True).data,
            "discounts": self._get_discount_serializer()(reservation_discounts, many=True).data,
        }

    def list(self, request, prop_id):
        dates = filters.DateFilter().get_query_params(self.request)
        occupancy = filters.OccupancyFilter().get_query_params(request)
        try:
            prop = self._get_property(request)
        except exceptions.ValidationError:
            return Response(
                data={"error": "invalid value for prop query param"}, status=HTTP_400_BAD_REQUEST
            )
        except exceptions.MultipleObjectsReturned:
            return Response(
                data={"error": "prop query param is required"}, status=HTTP_400_BAD_REQUEST
            )

        response_data = self._get_availability_response(
            prop=prop, occupancy=occupancy, dates=dates
        )

        if response_data["available"] or self.always_include_quote:
            try:
                response_data.update(self._get_quote_response(prop=prop, dates=dates))
            except ValueError:
                response_data.update({"available": False})
                return Response(data=response_data, status=HTTP_422_UNPROCESSABLE_ENTITY)

        return Response(response_data)


class BlockingViewSet(NestedPropertyCreateMixin, NestedViewSetMixin, viewsets.ModelViewSet):
    """Read, create, update and delete Blocking information."""

    serializer_class = serializers.BlockingSerializer
    queryset = models.Blocking.objects.all()
    filter_backends = (OrganizationFilter,)
    org_lookup_field = "prop__organization"


class TurndaysViewSet(NestedPropertyCreateMixin, NestedViewSetMixin, viewsets.ModelViewSet):
    """Read, create, update and delete Blocking information."""

    serializer_class = serializers.TurnDaySerializer
    queryset = models.TurnDay.objects.all()
    filter_backends = (OrganizationFilter,)
    org_lookup_field = "prop__organization"


class FeatureViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Create or List Features"""

    serializer_class = serializers.FeatureSerializer
    filter_backends = (filters.CategoryFilter,)
    pagination_class = PageNumberPagination

    @cache_result("feature_queryset_cache", 1800)
    def get_queryset(self):
        return models.Feature.objects.distinct("name").order_by("name")


class SeasonalRateViewSet(NestedPropertyCreateMixin, NestedViewSetMixin, viewsets.ModelViewSet):
    """Read, create, update and delete Blocking information."""

    serializer_class = serializers.SeasonalRateSerializer
    queryset = models.Rate.objects.filter(seasonal=True)
    filter_backends = (OrganizationFilter,)
    org_lookup_field = "prop__organization"


class SchedulingAssistantViewSet(
    NestedViewSetMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Read, update Job SchedulingAssistant information."""

    serializer_class = serializers.SchedulingAssistantSerializer
    queryset = models.SchedulingAssistant.objects.all()
    filter_backends = (OrganizationFilter,)
    org_lookup_field = "prop__organization"


class ReservationNoteViewSet(
    ApplicationPermissionViewMixin,
    NestedReservationCreateMixin,
    NestedViewSetMixin,
    viewsets.ModelViewSet,
):
    """Read, create, update and delete Reservation Note information."""

    serializer_class = serializers.ReservationNoteSerializer
    queryset = models.ReservationNote.objects.all()
    filter_backends = (OrganizationFilter, GroupAccessFilter)
    add_permissions = (GroupAccess,)
    org_lookup_field = "reservation__prop__organization"
    group_lookup_field = "reservation__prop__group"


class GroupUserAssignmentViewSet(viewsets.ModelViewSet):
    queryset = GroupUserAssignment.objects.all()
    serializer_class = serializers.GroupUserAssignmentSerializer


class ExternalListingViewSet(viewsets.ModelViewSet):
    queryset = ExternalListing.objects.all()
    serializer_class = serializers.ExternalListingSerializer

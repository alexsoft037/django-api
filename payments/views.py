from rest_framework import exceptions, status
from rest_framework.decorators import action
from rest_framework.mixins import (
    CreateModelMixin,
    DestroyModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
)
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ModelViewSet, ReadOnlyModelViewSet
from stripe.error import InvalidRequestError

from accounts.permissions import IsSuperUser
from cozmo_common.filters import CouponValidFilter, OrganizationFilter
from cozmo_common.mixins import ApplicationPermissionViewMixin
from . import models, serializers
from .services import Stripe
from .tasks import coupon_sync, disputes_sync


class BaseCreditCardViewSet(ModelViewSet):

    filter_backends = (OrganizationFilter,)

    def perform_destroy(self, instance):
        serializer = self.get_serializer(instance=instance)
        serializer.delete()


class CreditCardViewSet(BaseCreditCardViewSet):

    org_lookup_field = "customer__organization"

    queryset = models.CreditCard.objects.all()
    serializer_class = serializers.CreditCardSerializer


class GuestCreditCardViewSet(BaseCreditCardViewSet):

    org_lookup_field = "contact__organization"

    queryset = models.CreditCard.objects.all()
    serializer_class = serializers.GuestCreditCardSerializer


class PricingPlanViewSet(ReadOnlyModelViewSet):

    queryset = models.PricingPlan.objects.all()
    serializer_class = serializers.PricingPlanSerializer


class SubscribeViewSet(CreateModelMixin, DestroyModelMixin, ReadOnlyModelViewSet):

    serializer_class = serializers.SubscribeSerializer
    queryset = models.Subscription.objects.all()
    filter_backends = (OrganizationFilter,)

    org_lookup_field = "customer__organization"


class ChargeViewSet(CreateModelMixin, ReadOnlyModelViewSet):

    serializer_class = serializers.ChargeSerializer
    queryset = models.Charge.objects.all()
    filter_backends = (OrganizationFilter,)

    org_lookup_field = "organization"

    @action(detail=True, methods=["PATCH"], serializer_class=serializers.ChargeRefundSerializer)
    def refund(self, request, pk):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class DisputeViewSet(RetrieveModelMixin, ListModelMixin, GenericViewSet):

    queryset = models.Dispute.objects.all()
    serializer_class = serializers.DisputeSerializer
    pagination_class = PageNumberPagination
    org_lookup_field = "charge__organization"

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            resp = Stripe().update_dispute(instance.external_id, request.data)
        except Exception as e:
            return Response(status=status.HTTP_400_BAD_REQUEST, data=e.json_body)
        serializer = self.get_serializer(instance, data=resp)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=["POST"])
    def sync(self, request, pk):
        instance = self.get_object()
        resp = Stripe().retrieve_dispute(instance.external_id)
        serializer = self.get_serializer(instance, data=resp)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=False, methods=["POST"], permission_classes=[IsSuperUser])
    def sync_all(self, request):
        id = request.data.get("id")
        disputes_sync.delay(id)
        return Response()


class CouponViewSet(
    CreateModelMixin, DestroyModelMixin, RetrieveModelMixin, ListModelMixin, GenericViewSet
):
    class StripeError(exceptions.APIException):
        status_code = status.HTTP_400_BAD_REQUEST
        default_detail = "A stripe error"

    queryset = models.Coupon.objects.all()
    serializer_class = serializers.CouponSerializer
    pagination_class = PageNumberPagination
    filter_backends = (CouponValidFilter,)

    def perform_create(self, serializer):
        try:
            data = dict(serializer.validated_data)
            data["coupon_id"] = data.pop("external_id")
            Stripe().create_coupon(**data)
        except InvalidRequestError as e:
            raise CouponViewSet.StripeError(detail=e.json_body)
        except Exception:
            raise exceptions.APIException()
        super().perform_create(serializer)

    def perform_destroy(self, instance):
        try:
            Stripe().delete_coupon(instance.external_id)
        except InvalidRequestError as e:
            if e.code != "resource_missing":
                raise CouponViewSet.StripeError(detail=e.json_body)
        except Exception:
            raise exceptions.APIException()
        super().perform_destroy(instance)

    @action(detail=True, methods=["POST"])
    def sync(self, request, pk):
        instance = self.get_object()
        coupon = None
        try:
            coupon = Stripe().retrieve_coupon(instance.external_id)
        except InvalidRequestError as e:
            if e.code != "resource_missing":
                raise CouponViewSet.StripeError(detail=e.json_body)
        except Exception:
            raise exceptions.APIException()

        if not coupon:
            instance.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = self.get_serializer(instance, data=coupon.to_dict())
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=False, methods=["POST"])
    def sync_all(self, request):
        coupon_sync.delay()
        return Response()


class PlaidViewSet(CreateModelMixin, ReadOnlyModelViewSet):
    queryset = models.PlaidApp.objects.all()
    serializer_class = serializers.PlaidSerializer
    pagination_class = PageNumberPagination
    filter_backends = (OrganizationFilter,)


class PlaidTransactionViewSet(ReadOnlyModelViewSet):
    queryset = models.PlaidTransaction.objects.all()
    serializer_class = serializers.PlaidTransactionSerializer
    pagination_class = PageNumberPagination
    filter_backends = (OrganizationFilter,)

    @action(detail=True, methods=["POST"], serializer_class=serializers.MatchSerializer)
    def match(self, pk):
        pass


class BillingDetailsViewSet(ApplicationPermissionViewMixin, ListModelMixin, GenericViewSet):
    queryset = models.Subscription.objects.all()
    serializer_class = serializers.BillingSerializer
    filter_backends = (OrganizationFilter,)

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(request.user.organization.subscription.last())
        return Response(serializer.data)

    @action(
        detail=False, methods=["POST", "DELETE"], serializer_class=serializers.CreditCardSerializer
    )
    def method(self, request):
        if request.method == "POST":
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        else:
            cards = request.user.organization.customer.credit_cards.all()
            for card in cards:
                serializer = self.get_serializer(instance=card)
                serializer.delete()
            return Response(status=204)

    # @action(
    #     detail=False,
    #     methods=["GET"],
    #     serializer_class=serializers.ReceiptRequestSerializer,
    # )
    # def receipt(self, request):
    #     pass
    # @action(detail=False, methods=["POST"], serializer_class=serializers.InvoiceSerializer)
    # def invoice(self, request):
    #     pass

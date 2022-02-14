import json
from collections import namedtuple
from logging import getLogger
from secrets import token_urlsafe
from urllib.parse import urljoin

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import redirect
from requests.exceptions import HTTPError
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.mixins import DestroyModelMixin, ListModelMixin
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK
from rest_framework.viewsets import GenericViewSet

from cozmo_common.filters import OrganizationFilter
from rental_integrations.airbnb.serializers import MeUserSerializer
from rental_integrations.airbnb.service import AirbnbService
from . import models, serializers, services

logger = getLogger(__name__)
webhook_logger = getLogger("webhook")


class AppViewSet(ListModelMixin, GenericViewSet):
    """Read list of all integrations."""

    queryset = models.App.objects.all()
    serializer_class = serializers.AppSerializer


class OAuth2ViewSet(DestroyModelMixin, GenericViewSet):

    service_class = NotImplementedError
    serializer_class = NotImplementedError
    filter_backends = (OrganizationFilter,)
    url_class = namedtuple("Url", ["url"])

    def get_redirect_url(self, request, location=""):
        debug_redirect_url = None
        if settings.DEBUG and hasattr(settings, "DEBUG_REDIRECT_URL"):
            debug_redirect_url = "{}{}{}".format(
                getattr(settings, "DEBUG_REDIRECT_URL", None), request._request.path, location
            )
        return debug_redirect_url or request._request.build_absolute_uri(location=location)

    def perform_post_auth(self, **kwargs):
        pass

    def list(self, request, *args, **kwargs):
        state = token_urlsafe()
        cache.set(self.service_class.CACHE_KEY.format(state), request.user.id, 600)

        redirect_uri = self.get_redirect_url(request, "auth/")
        serializer = serializers.InstallUrlSerializer(
            instance=self.url_class(
                url=self.service_class.install_url(state=state, redirect_uri=redirect_uri)
            )
        )
        return Response(serializer.data)

    @action(methods=["GET"], detail=False, permission_classes=(AllowAny,))
    def auth(self, request, *args, **kwargs):
        success_url = urljoin(settings.COZMO_WEB_URL, "apps?success=1")
        error_url = urljoin(settings.COZMO_WEB_URL, "apps?success=0")
        if self.get_serializer_class() == serializers.AirbnbAccessSerializer:
            success_url = urljoin(settings.COZMO_WEB_URL, "channels/syncproperties")

        error = request.query_params.get("error", None)
        if error is not None:
            return redirect(error_url)

        verify_data = request.query_params.copy()
        verify_data["redirect_uri"] = self.get_redirect_url(request)
        verify = serializers.VerifyCodeSerializer(service=self.service_class(), data=verify_data)
        try:
            verify.is_valid(raise_exception=True)
            verification = verify.save()
        except ValidationError as e:
            return redirect(error_url)

        app = (
            self.get_serializer_class()
            .Meta.model.objects.filter(organization_id=verify._organization_id)
            .last()
        )
        if app:
            access = self.get_serializer(instance=app, data=verification)
        else:
            access = self.get_serializer(data=verification)
        if not access.is_valid():
            return redirect(error_url)
        access.save(organization_id=verify._organization_id)

        self.perform_post_auth(access=access)

        return redirect(success_url)


class SlackAuthViewSet(OAuth2ViewSet):
    """
    list:
        Read Slack App installation url.

    auth:
        Slack OAuth2 webhook.
    """

    service_class = services.Slack
    serializer_class = serializers.SlackAccessSerializer
    queryset = models.SlackApp.objects.all()


class GoogleAuthViewSet(OAuth2ViewSet):
    """
    list:
        Read Google App installation url.

    auth:
        Google OAuth2 webhook.
    """

    service_class = services.Google
    serializer_class = serializers.GoogleAccessSerializer
    queryset = models.GoogleApp.objects.all()


class StripeAuthViewSet(OAuth2ViewSet):
    """
    list:
        Read Stripe App installation url.

    auth:
        Stripe OAuth2 webhook.
    """

    service_class = services.Stripe
    serializer_class = serializers.StripeAccessSerializer
    queryset = models.StripeApp.objects.all()

    @action(
        methods=["POST"],
        detail=False,
        permission_classes=(AllowAny,),
        serializer_class=serializers.StripeUpdateSerializer,
    )
    def updates(self, request, *args, **kwargs):
        serializer = serializers.StripeUpdateSerializer(
            data={"signature": request._request.META.get("HTTP_STRIPE_SIGNATURE")},
            context={"payload": request.body},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=200)


class MailchimpAuthViewSet(OAuth2ViewSet):
    """
    list:
        Read Mailchimp App installation url.

    auth:
        Mailchimp OAuth2 webhook.
    """

    service_class = services.MailChimp
    serializer_class = serializers.MailChimpAccessSerializer
    queryset = models.MailChimpApp.objects.all()


class AirbnbAuthViewSet(OAuth2ViewSet):
    """
    list:
        Read Airbnb installation url.

    auth:
        Airbnb OAuth2 webhook.
    """

    service_class = services.Airbnb
    serializer_class = serializers.AirbnbAccessSerializer
    queryset = models.AirbnbAccount.objects.all()

    def perform_post_auth(self, **kwargs):
        access = kwargs.get("access")
        service = AirbnbService(
            access.validated_data["user_id"], access.validated_data["access_token"]
        )
        user_data = service.get_me_user()
        user_serializer = MeUserSerializer(data=user_data, context=access.instance)
        user_serializer.is_valid(raise_exception=True)
        user_serializer.save()

    def perform_destroy(self, instance):
        try:
            self.service_class().revoke_token(instance.access_token)
        except HTTPError:
            logger.warn("Can't remove Airbnb App %s", instance.id)
        else:
            super().perform_destroy(instance)


class AirbnbWebhookViewSet(GenericViewSet):

    permission_classes = (AllowAny,)
    lookup_field = "confirmation_code"

    def get_serializer_class(self):
        return {
            "GET": serializers.AirbnbAvailabilitySerializer,
            "POST": serializers.AirbnbReservationCallSerializer,
            "PUT": serializers.AirbnbReservationCallSerializer,
        }.get(self.request.method)

    def get_notification_serializer(*args, **kwargs):
        action = kwargs.get("data", {}).get("action", None)
        serializer_class = {
            "reservation_acceptance_confirmation": serializers.AirbnbReservationNotifySerializer,
            "reservation_cancellation_confirmation": serializers.AirbnbReservationNotifySerializer,
            "reservation_alteration_confirmation": serializers.AirbnbReservationNotifySerializer,
            "reservation_requested": serializers.AirbnbReservationNotifySerializer,
            "reservation_request_voided": serializers.AirbnbReservationNotifySerializer,
            "listing_approval_status_changed": serializers.AirbnbNotifyApprovalSerializer,
            "listing_synchronization_settings_updated": serializers.AirbnbNotifySyncSerializer,
            "listings_unlinked": serializers.AirbnbNotifyUnlinkedSerializer,
            "authorization_revoked": serializers.AirbnbNotifyAuthRevokedSerializer,
            "message_added": serializers.AirbnbNotifyMessageAddedSerializer,
            # "payout_notification": serializers.AirbnbPayoutNotifySerializer
        }.get(action, serializers.AirbnbNotifySerializer)
        return serializer_class(*args, **kwargs)

    def list(self, request, *args, **kwargs):
        """Airbnb Availability webhook"""
        webhook_logger.info("[webhook] - (Reservation) Payload - %s", json.dumps(request.data))
        serializer = self.get_serializer(data=request.query_params)
        webhook_logger.info(
            "[webhook] - (Reservation) Handler - %s", str(serializer.__class__.__name__)
        )
        if serializer.is_valid():
            response = Response(status=HTTP_200_OK, data=serializer.save())
        else:
            response = Response(status=HTTP_200_OK, data=serializer._failure)
        webhook_logger.info(
            "[webhook] - (Reservation) Response - (%s) %s", HTTP_200_OK, str(response.data)
        )
        return response

    def create(self, request, *args, **kwargs):
        """Airbnb Reservation webhook"""
        webhook_logger.info("[webhook] - (Reservation) Payload - %s", json.dumps(request.data))
        serializer = self.get_serializer(data=request.data)
        webhook_logger.info(
            "[webhook] - (Reservation) Handler - %s", str(serializer.__class__.__name__)
        )
        if serializer.is_valid():
            response = Response(status=HTTP_200_OK, data=serializer.save())
        else:
            response = Response(status=HTTP_200_OK, data=serializer._failure)
        webhook_logger.info(
            "[webhook] - (Reservation) Response - (%s) %s", HTTP_200_OK, str(response.data)
        )
        return response

    def update(self, request, confirmation_code=None, *args, **kwargs):
        """Airbnb Reservation webhook"""
        webhook_logger.info("[webhook] - (Reservation) Payload - %s", json.dumps(request.data))
        serializer = self.get_serializer_class().with_instance(confirmation_code, request.data)
        webhook_logger.info(
            "[webhook] - (Reservation) Handler - %s", str(serializer.__class__.__name__)
        )
        if serializer.is_valid():
            response = Response(status=HTTP_200_OK, data=serializer.save())
        else:
            response = Response(status=HTTP_200_OK, data=serializer._failure)
        webhook_logger.info(
            "[webhook] - (Reservation) Response - (%s) %s", HTTP_200_OK, str(response.data)
        )
        return response

    @action(
        methods=["POST"],
        detail=False,
        #  authentication_classes=[AirbnbAuthentication],  # TODO Looks like not used by Airbnb
        get_serializer=get_notification_serializer,
    )
    def notification(self, request, *args, **kwargs):
        webhook_logger.info("[webhook] - (Notification) Payload - %s", json.dumps(request.data))
        serializer = self.get_serializer(data=request.data, context=self.get_serializer_context())
        webhook_logger.info(
            "[webhook] - (Notification) Handler - %s", str(serializer.__class__.__name__)
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        webhook_logger.info(
            "[webhook] - (Notification) Response - (%s) %s", HTTP_200_OK, str(serializer._success)
        )
        return Response(status=HTTP_200_OK, data=serializer._success)

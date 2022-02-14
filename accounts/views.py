"""Module provides views for User-related requests."""
from allauth.account.models import EmailConfirmationHMAC
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from django.contrib.auth import login
from guardian.models import UserObjectPermission
from rest_auth.app_settings import JWTSerializer
from rest_auth.registration import views as register_views
from rest_auth.registration.serializers import VerifyEmailSerializer
from rest_auth.utils import jwt_encode
from rest_auth.views import LoginView
from rest_framework import mixins, status, viewsets
from rest_framework.generics import GenericAPIView
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.serializers import PhoneLoginSerializer
from cozmo_common.filters import OrganizationFilter
from . import serializers
from .models import OrgMembership, Token
from .permissions import IsOrganizationManager


class GoogleLogin(register_views.SocialLoginView):
    """Implementation of Google social login."""

    adapter_class = GoogleOAuth2Adapter


class PhoneLoginView(LoginView):
    serializer_class = PhoneLoginSerializer


class UserInviteView(register_views.RegisterView):

    serializer_class = serializers.UserInviteSerializer
    permission_class = (IsOrganizationManager,)
    filter_backends = (OrganizationFilter,)
    org_lookup_field = "organizations"

    def get_response_data(self, user):
        return {"detail": "Invitation e-mail sent."}


class UserInviteSignupView(LoginView):

    serializer_class = serializers.UserInviteSignupSerializer
    permission_class = (IsOrganizationManager,)
    filter_backends = (OrganizationFilter,)
    org_lookup_field = "organizations"

    def post(self, request, *args, **kwargs):
        self.request = request
        self.serializer = self.get_serializer(data=self.request.data, context={"request": request})
        self.serializer.is_valid(raise_exception=True)

        self.login()
        return self.get_response()


class TokenViewSet(viewsets.ModelViewSet):

    queryset = Token.objects.all()
    serializer_class = serializers.TokenSerializer
    filter_backends = (OrganizationFilter,)


class PermissionViewSet(
    mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.ReadOnlyModelViewSet
):

    queryset = UserObjectPermission.objects.exclude(user__token=None)
    serializer_class = serializers.PermissionSerializer
    filter_backends = (OrganizationFilter,)
    org_lookup_field = "user__organizations"


class GetInvitationView(RetrieveModelMixin, GenericAPIView):

    serializer_class = VerifyEmailSerializer
    permission_classes = (AllowAny,)

    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=kwargs, context={"request": request})
        serializer.is_valid(raise_exception=True)

        instance = EmailConfirmationHMAC.from_key(serializer.validated_data["key"])
        if not instance:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        verified = instance.email_address.verified
        user = instance.email_address.user
        invited = user.invited

        verification_status = "not_allowed"
        if verified:
            verification_status = "verified"
        elif invited and not verified:
            verification_status = "invitation_not_verified"
        elif not invited and not verified:
            verification_status = "not_verified"

        return Response({"status": verification_status})


class VerifyEmailView(register_views.VerifyEmailView):
    def get_serializer(self, *args, **kwargs):
        return serializers.VerifyEmailSerializer(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        self.kwargs["key"] = serializer.validated_data["key"]
        confirmation = self.get_object()
        instance = serializer.save(confirmation=confirmation)

        user = instance.email_address.user

        user.backend = "django.contrib.auth.backends.ModelBackend"
        token = jwt_encode(user)
        login(request, user)
        data = {"user": user, "token": token}
        serializer = JWTSerializer(instance=data, context={"request": self.request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class OrgMembershipViewSet(viewsets.ModelViewSet):
    queryset = OrgMembership.objects.all()
    serializer_class = serializers.OrgMembershipSerializer

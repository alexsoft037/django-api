import jwt
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.utils.encoding import smart_text
from django.utils.translation import ugettext as _
from jwt.exceptions import DecodeError
from rest_framework import exceptions
from rest_framework.authentication import get_authorization_header
from rest_framework_jwt import authentication as jwt_auth

from accounts.utils import jwt_decode_handler
from .models import Token

User = get_user_model()


class APITokenAuthentication(jwt_auth.BaseJSONWebTokenAuthentication):

    auth_header_prefix = "Token:"

    www_authenticate_realm = "api"

    def get_jwt_value(self, request):
        try:
            header_prefix, token = get_authorization_header(request).split()
        except ValueError:
            return None

        if smart_text(header_prefix) != self.auth_header_prefix:
            return None

        try:
            Token.objects.filter(key=token.decode("utf-8")).get()
        except (ValidationError, Token.DoesNotExist):
            return None

        return token

    def authenticate_header(self, request):
        return '{} realm="{}"'.format(self.auth_header_prefix, self.www_authenticate_realm)


class ShadowJWTAuthentication(jwt_auth.JSONWebTokenAuthentication):
    def authenticate(self, request):
        auth = super().authenticate(request)

        try:
            user, raw_jwt = auth
        except TypeError:
            return auth

        try:
            jwt = jwt_decode_handler(raw_jwt)
        except DecodeError:
            jwt = {}

        is_superuser = User.objects.filter(id=jwt.get("user_id"), is_superuser=True).exists()
        shadow_user = User.objects.filter(id=jwt.get("shadow")).first()

        if is_superuser and shadow_user:
            user = shadow_user

        return user, raw_jwt


class PublicJWTAuthentication(jwt_auth.JSONWebTokenAuthentication):
    def authenticate(self, request):
        jwt_value = self.get_jwt_value(request)
        if jwt_value is None:
            return None

        try:
            payload = jwt_decode_handler(jwt_value)
        except jwt.ExpiredSignature:
            msg = _("Signature has expired.")
            raise exceptions.AuthenticationFailed(msg)
        except jwt.DecodeError:
            msg = _("Error decoding signature.")
            raise exceptions.AuthenticationFailed(msg)
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed()

        if "type" in payload:
            request.token_payload = payload
            return AnonymousUser(), jwt_value

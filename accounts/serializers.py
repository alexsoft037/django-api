"""Module provides serializers for User-related requests."""

from allauth.account import app_settings as allauth_settings
from allauth.account.adapter import get_adapter
from allauth.account.utils import setup_user_email
from allauth.utils import email_address_exists, import_callable
from django.apps import apps
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ValidationError as DjValidationError
from django.utils.translation import ugettext_lazy as _
from guardian.models import UserObjectPermission
from guardian.shortcuts import assign_perm
from rest_auth import serializers as auth_serializers
from rest_auth.registration import serializers as register_serializers
from rest_auth.serializers import LoginSerializer
from rest_framework import exceptions, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.fields import (
    BooleanField,
    ChoiceField,
    CurrentUserDefault,
    HiddenField,
    IntegerField,
)

from accounts.choices import RoleTypes
from accounts.signals import user_role_changed
from cozmo_common.db.fields import PhoneField as DbPhoneField
from cozmo_common.fields import ChoicesField, DefaultOrganization, ModelChoicesField, PhoneField, \
    E164PhoneField
from cozmo_common.functions import send_email
from listings.models import GroupUserAssignment
from .forms import PasswordResetForm
from .models import OrgMembership, Token

User = get_user_model()


class UserDataSerializer(serializers.ModelSerializer):
    """User model w/o password."""

    avatar = serializers.URLField()
    account_type = ChoicesField(choices=User.AllowedTypes.choices())
    phone = E164PhoneField(allow_null=True, required=False)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "account_type",
            "avatar",
            "email",
            "phone",
            "first_name",
            "last_name",
            "is_active",
        )
        read_only_fields = ("email",)

    def __new__(cls, *args, **kwargs):
        cls.serializer_field_mapping[DbPhoneField] = PhoneField
        return super().__new__(cls, *args, **kwargs)

    def update(self, instance, validated_data):
        username = validated_data.get("username")
        if username:
            email, _ = instance.emailaddress_set.get_or_create(user=instance, email=username)
            email.send_confirmation()
            del validated_data["username"]
        return super().update(instance, validated_data)


class RegisterSerializer(serializers.ModelSerializer):
    """User registration data.

    Substitutes default `rest_auth.registration.serializers.RegisterSerializer`.
    """

    phone = E164PhoneField(required=False, allow_null=True)
    role = ChoiceField(
        choices=RoleTypes.choices(),
        default=RoleTypes.owner.value,
        write_only=True,
        allow_null=True,
    )

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "password", "phone", "role")
        extra_kwargs = {
            "password": {"write_only": True},
            "email": {"required": allauth_settings.EMAIL_REQUIRED},
            "first_name": {"required": False},
            "last_name": {"required": False},
        }

    def validate_email(self, email):
        """Check if provided email is valid to use as email and username."""
        email = get_adapter().clean_email(email)
        email = get_adapter().clean_username(email)
        if email and email_address_exists(email):
            raise serializers.ValidationError(
                _("A user is already registered with this e-mail address.")
            )
        return email

    def validate_password(self, password):
        """Check if provided password is valid."""
        return get_adapter().clean_password(password)

    def validate(self, data) -> dict:
        """Check if provided data is valid.

        This includes dependencies between each piece of data. Returns
        validated data.
        """
        organization = data.pop("organization", None)
        user = User(**data)
        password = data.get("password", None)

        errors = dict()
        try:
            if password is not None:
                get_adapter().clean_password(password, user)
        except (serializers.ValidationError, DjValidationError) as e:
            errors["password"] = list(e.messages)

        if errors:
            raise serializers.ValidationError(errors)

        if organization:
            data["organization"] = organization

        return super().validate(data)

    def get_cleaned_data(self) -> dict:
        """Return validated data.

        `is_valid` method must be called first.

        """
        validated_data = self.validated_data.copy()
        data = {
            "password": validated_data.pop("password", None),
            "email": validated_data.pop("email", ""),
            "first_name": validated_data.pop("first_name", ""),
            "last_name": validated_data.pop("last_name", ""),
            "phone": validated_data.pop("phone", None),
            "organization": validated_data.pop("organization", None),
        }
        data.update(validated_data)
        return data

    def save(self, request=None):
        if self.instance is not None:
            self.instance = self.update(self.instance, self.validated_data)
        else:
            self.instance = self.create(request)

        return self.instance

    def create(self, request) -> User:
        """Create proper user instance based on provided input."""
        adapter = get_adapter()
        user = adapter.new_user(request)
        self.cleaned_data = self.get_cleaned_data()
        for attr, value in self.cleaned_data.items():
            setattr(user, attr, value)
        user = adapter.save_user(request, user, self)

        user_role_changed.send(sender=user.__class__, instance=user)

        setup_user_email(request, user, [])
        return user


class UserInviteSerializer(RegisterSerializer):

    account_type = ChoicesField(
        choices=User.AllowedTypes.choices(), default=User.AllowedTypes.Small_Owner.value
    )
    organization = HiddenField(default=DefaultOrganization())
    role = ChoicesField(choices=RoleTypes.choices())
    group_ids = serializers.ListField(
        child=IntegerField(), write_only=True, allow_empty=True, required=False
    )
    invited = BooleanField(default=True)

    class Meta(RegisterSerializer.Meta):
        fields = (
            "email",
            # "first_name",
            # "last_name",
            # "phone",
            "account_type",
            "role",
            "organization",
            "invited",
            "group_ids",
        )

    def create(self, request):
        groups = request.data.pop("group_ids", None)
        user = super().create(request)
        if groups is not None:
            for group_id in groups:
                GroupUserAssignment.objects.update_or_create(group_id=group_id, user_id=user.id)
        return user

    def validate(self, data) -> dict:
        group_ids = data.pop("group_ids", None)

        validated_data = super().validate(data)

        if group_ids:
            validated_data["group_ids"] = group_ids

        return validated_data


class UserInviteSignupSerializer(LoginSerializer):

    organization = HiddenField(default=DefaultOrganization())
    key = serializers.CharField(max_length=64)
    first_name = serializers.CharField(max_length=64, required=False)
    last_name = serializers.CharField(max_length=64, required=False)

    # class Meta:
    #     model = User
    #     fields = (
    #         "key",
    #         "first_name",
    #         "last_name",
    #         "password",
    #         # "phone",
    #     )
    #     extra_kwargs = {
    #         "password": {"write_only": True},
    #         "first_name": {"required": False},
    #         "last_name": {"required": False},
    #     }

    def validate(self, data) -> dict:
        """Check if provided data is valid.

        This includes dependencies between each piece of data. Returns
        validated data.
        """
        organization = data.pop("organization", None)
        user = User(**data)
        password = data.get("password", None)

        errors = dict()
        try:
            if password is not None:
                get_adapter().clean_password(password, user)
        except (serializers.ValidationError, DjValidationError) as e:
            errors["password"] = list(e.messages)

        if errors:
            raise serializers.ValidationError(errors)

        if organization:
            data["organization"] = organization

        return super().validate(data)

    # def create(self, request) -> User:
    #     """Create proper user instance based on provided input."""
    #     adapter = get_adapter()
    #     user = adapter.new_user(request)
    #     self.cleaned_data = self.get_cleaned_data()
    #     for attr, value in self.cleaned_data.items():
    #         setattr(user, attr, value)
    #     user = adapter.save_user(request, user, self)
    #     setup_user_email(request, user, [])
    #     return user


class PasswordResetSerializer(auth_serializers.PasswordResetSerializer):

    password_reset_form_class = PasswordResetForm

    def save(self):
        request = self.context.get("request")
        # Set some values to trigger the send_email method.
        opts = {
            "use_https": request.is_secure(),
            "from_email": getattr(settings, "DEFAULT_FROM_EMAIL"),
            "request": request,
            "html_email_template_name": "registration/password_reset_email.html",
        }

        self.reset_form.save(**opts)


class PhoneLoginSerializer(auth_serializers.LoginSerializer):
    phone = PhoneField(required=False, allow_blank=True)

    def _validate_phone(self, phone, password):

        if phone and password:
            user = authenticate(username=phone, password=password)
        else:
            msg = _('Must include "phone" and "password".')
            raise exceptions.ValidationError(msg)

        return user

    def validate(self, attrs):
        phone = attrs.get("phone")
        password = attrs.get("password")

        user = self._validate_phone(phone, password)

        # Did we get back an active user?
        if user:
            if not user.is_active:
                msg = _("User account is disabled.")
                raise exceptions.ValidationError(msg)
        else:
            msg = _("Unable to log in with provided credentials.")
            raise exceptions.ValidationError(msg)

        attrs["user"] = user
        return attrs


class PermissionSerializer(serializers.ModelSerializer):

    permission_for = ModelChoicesField(
        source="content_object",
        choices=(("rental_connections.RentalConnection", "RentalConnection"),),
    )
    token_id = serializers.IntegerField(source="user.token.id")
    organization = HiddenField(default=DefaultOrganization())

    class Meta:
        model = UserObjectPermission
        fields = ("id", "permission_for", "permission_for_id", "token_id", "organization")
        extra_kwargs = {"permission_for_id": {"source": "object_pk"}}

    def validate(self, data):
        try:
            data["user_id"] = Token.objects.values("user_id").get(
                id=data.pop("user")["token"]["id"], organization_id=data["organization"]
            )["user_id"]
        except Token.DoesNotExist:
            raise serializers.ValidationError({"token_id": "Not found"})

        PermissionFor = apps.get_model(data["content_object"])
        try:
            data["content_object"] = PermissionFor.objects.get(
                id=data["object_pk"], organization_id=data["organization"]
            )
        except PermissionFor.DoesNotExist:
            raise serializers.ValidationError({"permission_for_id": "Not found"})

        return data

    def create(self, data):
        permission = assign_perm(
            "public_api_access", User.objects.get(id=data["user_id"]), data["content_object"]
        )

        return permission


class TokenSerializer(serializers.ModelSerializer):

    created_by = HiddenField(default=CurrentUserDefault())
    organization = HiddenField(default=DefaultOrganization())

    class Meta:
        model = Token
        fields = ("id", "key", "name", "created_by", "is_sandbox", "organization")
        extra_kwargs = {"key": {"read_only": True}}


class PasswordResetConfirmSerializer(auth_serializers.PasswordResetConfirmSerializer):
    def save(self):
        super().save()
        send_email(
            "account/email/email_confirmation_password_change.html",
            {"user": self.user},
            "Voyajoy - Email Confirmation",
            getattr(self.user, "email", None),
        )


class InvitationSerializer(serializers.ModelSerializer):
    pass


class VerifyUserSerializer(serializers.Serializer):
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    password = serializers.CharField()


class VerifyEmailSerializer(register_serializers.VerifyEmailSerializer):
    user = VerifyUserSerializer(required=False)

    def create(self, validated_data):
        user_data = validated_data.pop("user", None)
        instance = validated_data.pop("confirmation")
        if not user_data and instance.email_address.user.invited:
            raise ValidationError("User is invited, password must be included")
        if instance.email_address.verified:
            raise ValidationError("User account is already verified")
        instance.confirm(self.context["request"])
        instance.email_address.set_as_primary()
        user = instance.email_address.user
        user.username = instance.email_address.email

        if user_data:
            user.set_password(user_data["password"])
            user.first_name = user_data["first_name"]
            user.last_name = user_data["last_name"]
        user.save()
        return instance


class OrgMembershipSerializer(serializers.ModelSerializer):

    parent = HiddenField(default=DefaultOrganization())
    created_by = HiddenField(default=CurrentUserDefault())

    class Meta:
        model = OrgMembership
        fields = ("id", "parent", "child", "created_by")


class DefaultOrganizationSubscriptionSerializer(serializers.Serializer):

    is_active = BooleanField(default=True)


OrganizationSubscriptionSerializer = import_callable(
    getattr(settings, "APP_SERIALIZERS", {}).get(
        "ORGANIZATION_SUBSCRIPTION_SERIALIZER", DefaultOrganizationSubscriptionSerializer
    )
)

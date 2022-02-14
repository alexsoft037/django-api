from urllib.parse import urljoin

from allauth.account import app_settings as allauth_settings
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.utils import user_username
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import ValidationError as DjValidationError
from django.core.validators import validate_email
from guardian.shortcuts import assign_perm
from rest_framework.exceptions import ValidationError

from accounts.choices import RoleTypes
from .app_access import DEFAULT_APPS
from .models import Membership, Organization
from .permissions import MANAGE_ORGANIZATION_PERMISSION

_confirmation_url = urljoin(settings.COZMO_WEB_URL, "signup/account-verification?key={key}")


def _create_organization(user, organization=None):
    if organization is None:
        organization = Organization.objects.create(applications=DEFAULT_APPS, email=user.email)
    Membership.objects.create(user=user, organization=organization, is_default=True)
    user.organization = organization
    assign_perm(MANAGE_ORGANIZATION_PERMISSION, user, organization)


class AccountAdapter(DefaultAccountAdapter):
    """Performs common operations on `accounts.User` model."""

    def clean_email(self, email):
        try:
            validate_email(email)
        except DjValidationError as e:
            raise ValidationError(e.message)
        return email

    def get_email_confirmation_url(self, request, emailconfirmation):
        """Construct the email confirmation (activation) url for Cozmo Web."""
        return _confirmation_url.format(key=emailconfirmation.key)

    def populate_username(self, request, user):
        super().populate_username(request, user)
        if allauth_settings.USER_MODEL_USERNAME_FIELD:
            user_username(
                user,
                user.email
                or self.generate_unique_username(
                    user, [user.first_name, user.last_name, user.email, "user"]
                ),
            )

    def save_user(self, request, user, form, commit=True):
        """Save a new `accounts.User` instance using information from the signup form."""
        # we don't ask user to type password twice
        form.cleaned_data["password1"] = form.cleaned_data["password"]
        # we use email as username
        form.cleaned_data["username"] = form.cleaned_data["email"]
        user = super().save_user(request, user, form, commit=False)

        user.phone = form.cleaned_data["phone"]

        if commit:
            user.save()
            _create_organization(user, organization=form.cleaned_data["organization"])
        return user

    def send_confirmation_mail(self, request, emailconfirmation, signup):
        current_site = get_current_site(request)
        activate_url = self.get_email_confirmation_url(request, emailconfirmation)
        user = emailconfirmation.email_address.user
        ctx = {
            "user": user,
            "activate_url": activate_url,
            "current_site": current_site,
            "key": emailconfirmation.key,
        }
        invited = user.invited

        if invited:
            role = user.role
            invitation_email_templates_by_role = {
                RoleTypes.cleaner.value: "vendors/email/vendor_invitation",
                RoleTypes.property_owner.value: "owners/email/owner_invitation",
            }
            default_template = "account/email/email_invitation"
            ctx.update(
                {
                    "inviter_email": request.user.email,
                    "inviter_name": request.user.get_full_name(),
                    "inviter_org": request.user.organization.name,
                    "app_name": settings.APP_NAME
                }
            )
            email_template = invitation_email_templates_by_role.get(role, default_template)
        elif signup:
            email_template = "account/email/email_confirmation_signup"
        else:
            email_template = "account/email/email_confirmation"
        self.send_mail(email_template, emailconfirmation.email_address.email, ctx)


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """Perform common operations on social accounts linked to `accounts.User` model."""

    def populate_user(self, request, sociallogin, data):
        """Further populate the user instance.

        Tries to link a new social account
        with existing user.
        """
        User = get_user_model()
        try:
            # try to link a new sociallogin with an existing
            # account registered by username
            user = User.objects.get(username=data.get("username"))
            sociallogin.user = user
        except User.DoesNotExist:
            user = super().populate_user(request, sociallogin, data)
        return user

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form=form)

        if not user.organizations.exists():
            _create_organization(user)

        #  For open beta, we are temporarily disabling onboarding email [COZ-1894]
        #  send_email(
        #      "account/email/email_onboarding.html",
        #      {"user": user},
        #      "Voyajoy - Email Confirmation",
        #      getattr(user, "email", None),
        #  )
        return user

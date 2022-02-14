import os
import secrets
import urllib.parse
from collections import namedtuple

from django.apps import apps
from django.conf import settings
from django.conf.urls import url
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.core.cache import cache
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html

from accounts.signals import _set_user_permissions
from .models import Organization, User

ModelMapping = namedtuple("ModelMapping", ("name", "model", "lookup_field"))

model_mapper = {
    "Property": ModelMapping(
        name="Property", model="listings.Property", lookup_field="organization"
    ),
    "Reservation": ModelMapping(
        name="Reservation", model="listings.Reservation", lookup_field="prop__organization"
    ),
}


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = UserAdmin.list_display + (
        "organization",
        "account_actions",
        "reset_perms_action",
        "login_as",
    )
    custom_fieldsets = ((None, {"fields": ("account_type", "role")}),)

    def get_fieldsets(self, request, obj=None):
        return self.custom_fieldsets + super().get_fieldsets(request, obj)

    def reset_permissions(self, request, user_id, *args, **kwargs):
        _set_user_permissions(User.objects.get(pk=user_id))
        return HttpResponseRedirect(reverse("admin:accounts_user_changelist"))

    def remove_related(self, request, user_id, *args, **kwargs):
        if request.method == "POST":
            if os.environ.get("DJANGO_SETTINGS_MODULE") != "cozmo.settings_production":
                model_to_wipe = model_mapper.get(request.POST.get("models"))
                model = apps.get_model(*model_to_wipe.model.split("."))
                model.objects.filter(**{model_to_wipe.lookup_field: user_id}).delete()

            url = reverse("admin:accounts_user_changelist", current_app=self.admin_site.name)
            return HttpResponseRedirect(url)
        context = self.admin_site.each_context(request)

        context["opts"] = self.model._meta
        context["models"] = model_mapper.keys()
        context["title"] = "Wipe out"
        return TemplateResponse(request, "account/account_action.html", context)

    def login_as_do(self, request, user_id, *args, **kwargs):
        secret = secrets.token_urlsafe(nbytes=45)
        params = urllib.parse.urlencode({"secret": secret})
        url = urllib.parse.urljoin(settings.COZMO_WEB_URL, "shadow")

        cache.set(f"shadow_{secret}", f"{user_id},{request.user.id}", 10)
        return HttpResponseRedirect(f"{url}?{params}")

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            url(
                r"^(?P<user_id>.+)/remove-related/$",
                self.admin_site.admin_view(self.remove_related),
                name="remove-related",
            ),
            url(
                r"^(?P<user_id>.+)/login-as/$",
                self.admin_site.admin_view(self.login_as_do),
                name="login-as",
            ),
            url(
                r"^(?P<user_id>.+)/reset-permissions/$",
                self.admin_site.admin_view(self.reset_permissions),
                name="reset-permissions",
            ),
        ]
        return custom_urls + urls

    def account_actions(self, obj):
        return format_html(
            '<a class="button" href="{}">Remove Related</a>&nbsp;',
            reverse("admin:remove-related", args=[obj.pk]),
        )

    account_actions.short_description = "User Actions"
    account_actions.allow_tags = True

    def reset_perms_action(self, obj):
        return format_html(
            '<a class="button" href="{}">Reset</a>&nbsp;',
            reverse("admin:reset-permissions", args=[obj.pk]),
        )

    reset_perms_action.short_description = "Permissions"
    reset_perms_action.allow_tags = True

    def login_as(self, obj):
        if obj.is_superuser or obj.is_staff:
            to_render = ""
        else:
            to_render = format_html(
                '<a class="button" href="{}">Login as</a>&nbsp;',
                reverse("admin:login-as", args=[obj.pk]),
            )
        return to_render

    login_as.short_description = "Shadow login"
    login_as.allow_tags = True


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    # TODO override application choice field
    pass

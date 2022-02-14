from contextlib import contextmanager
from enum import Enum
from importlib import import_module
from operator import xor

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework import permissions
from rest_framework.permissions import IsAuthenticated

from .app_access import APP_ACCESS


class OrganizationPermissions(str, Enum):

    owner = "Can manage and delete organization and users"
    admin = "Can manage organization and users"
    contributor = "Can read and write all data besides users"
    developer = "Can access API and read all data besides organization and users"
    contractor = "Can read properties calendars"
    analyst = "Can read all data besides organization and users"

    @property
    def name(self):
        name = super().name
        return f"organization_{name}"

    @classmethod
    def choices(cls):
        return tuple((field.name, field.value) for field in cls)


MANAGE_ORGANIZATION_PERMISSION = OrganizationPermissions.owner.name


@contextmanager
def raise_403_instead_404():
    try:
        yield
    except Http404:
        raise PermissionDenied()


class HasApplicationAccess(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        view_class_module = view.__class__.__module__
        view_class_name = view.__class__.__name__
        if user and user.is_authenticated:
            if settings.DEBUG or user.is_superuser:
                return True
            for app in user.organization.applications:
                module = APP_ACCESS[app].get(view_class_module, {})
                if view_class_name in module:
                    ser = module[view_class_name].get("serializer")
                    if ser:
                        view.serializer_class = getattr(import_module(ser[0]), ser[1])
                    return True
        return True  # FIXME COZ-1970 APP_ACCESS dict is not a good idea


class IsOrganizationManager(permissions.BasePermission):
    def has_permission(self, request, view):
        has_perm = False
        user = request.user

        if user and user.is_authenticated and not user.is_vendor:
            has_perm = any(
                (
                    request.method in permissions.SAFE_METHODS,
                    user.has_perm(OrganizationPermissions.owner.name, user.organization),
                    user.has_perm(OrganizationPermissions.admin.name, user.organization),
                )
            )

        return has_perm


class IsSuperUser(permissions.BasePermission):
    def has_permission(self, request, view):
        has_perm = False
        user = request.user
        if user and user.is_authenticated and user.is_superuser:
            has_perm = True
        return has_perm


class IsVendorOrManager(permissions.BasePermission):
    def has_permission(self, request, view):
        has_perm = False
        user = request.user

        if user:
            has_perm = user.is_authenticated and any(
                (
                    request.method in permissions.SAFE_METHODS,
                    user.has_perm(OrganizationPermissions.contractor.name, user.organization),
                    user.has_perm(OrganizationPermissions.owner.name, user.organization),
                    user.has_perm(OrganizationPermissions.admin.name, user.organization),
                    user.has_perm(OrganizationPermissions.contributor.name, user.organization),
                )
            )

        return has_perm


class IsPublicApiUser(permissions.BasePermission):
    def has_permission(self, request, view):
        has_perm = False
        user = request.user
        if user and user.is_authenticated and (user.is_api_user or settings.DEBUG):
            is_sandbox_view = view.__module__.endswith("_sandbox")
            if settings.DEBUG or not xor(user.token.is_sandbox, is_sandbox_view):
                has_perm = True
        return has_perm


class HasPublicApiAccess(IsPublicApiUser, permissions.DjangoObjectPermissions):

    perms_map = dict.fromkeys(
        ["GET", "OPTIONS", "HEAD", "POST", "PATCH", "PUT", "DELETE"], ["public_api_access"]
    )

    def has_object_permission(self, request, view, obj):
        rental_connection = getattr(obj, "rental_connection", None)
        if rental_connection is None:
            return True

        with raise_403_instead_404():
            return super().has_object_permission(request, view, rental_connection)


class GroupAccess(IsAuthenticated, permissions.DjangoObjectPermissions):
    perms_map = dict.fromkeys(
        ["GET", "OPTIONS", "HEAD", "POST", "PATCH", "PUT", "DELETE"], ["group_access"]
    )

    default_group_lookup_field = "group"

    def has_object_permission(self, request, view, obj):
        is_group_contributor = request.user.is_group_contributor
        if not is_group_contributor:
            return True
        group_field = getattr(view, "group_lookup_field", self.default_group_lookup_field)
        group = getattr(obj, group_field, None)
        if group is None:
            return True

        with raise_403_instead_404():
            return super().has_object_permission(request, view, group)

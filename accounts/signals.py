from copy import deepcopy

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.dispatch import Signal, receiver

from accounts.choices import ApplicationTypes, RoleTypes
from accounts.models import Organization

user_role_changed = Signal(providing_args=["instance"])
subscription_started = Signal(providing_args=["instance"])
property_activated = Signal(providing_args=["instance"])
org_feature_changed = Signal(providing_args=["instance"])
org_user_types = [
    RoleTypes.owner.value,
    RoleTypes.admin.value,
    RoleTypes.contributor.value,
    RoleTypes.contributor_group.value,
]


def _get_perms(role, apps):
    role_name = {
        RoleTypes.owner.value: "owner",
        RoleTypes.admin.value: "admin",
        RoleTypes.contributor.value: "agent",
        RoleTypes.contributor_group.value: "agent",
        RoleTypes.cleaner.value: "vendor",
        RoleTypes.property_owner.value: "agent",
    }.get(role, "default")

    role_perms = deepcopy(settings.USER_ROLES.get(role_name, {}))

    if role in org_user_types:
        # Check organization app/features to set user permissions
        app_perms = settings.APP_USER_PERMS
        app_role = {
            # Disable Reservation for now since separating it is quite complicated.
            # It will ship by default for all accounts
            # ApplicationTypes.Reservation.value: "reservation",
            ApplicationTypes.Owners.value: "owner",
            ApplicationTypes.Vendors.value: "vendor",
        }
        all_apps = app_role.values()
        apps = [app_role.get(app) for app in apps if app_role.get(app, None)]
        missing_apps = list(set(all_apps) - set(apps))
        missing_app_perms = [app_perms.get(app) for app in missing_apps]

        # Modify role permissions based on available apps
        for perms in missing_app_perms:
            for app_label, models in perms.items():
                app = role_perms.get(app_label)
                for model in models:
                    if model in app:
                        del app[model]

    return role_perms


def _set_user_permissions(instance):
    # Get permissions
    role_perms = _get_perms(instance.role, instance.organization.applications)

    # Clear all permissions for user
    instance.user_permissions.clear()

    # Set user permissions
    for app_label, model_permissions in role_perms.items():
        for name, access_set in model_permissions.items():
            for access in access_set:
                instance.user_permissions.add(
                    Permission.objects.get(
                        content_type__app_label=app_label, codename=f"{access}_{name}"
                    )
                )


@receiver(user_role_changed, sender=get_user_model())
def apply_user_permissions(sender, instance, **kwargs):
    _set_user_permissions(instance)


@receiver(org_feature_changed, sender=Organization)
def apply_org_app_permissions(sender, instance, **kwargs):
    users = instance.user_set.filter(role__in=org_user_types)
    for user in users:
        apply_user_permissions(get_user_model(), user)

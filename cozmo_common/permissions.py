from rest_framework.permissions import DjangoModelPermissions

from accounts.permissions import IsOrganizationManager


class IsOrgAllowedToRead(IsOrganizationManager):
    def has_object_permission(self, request, view, obj):
        assert hasattr(view, "get_object_organization"), \
            "get_object_organization definition is required"
        return request.user.organization == view.get_object_organization(obj)


class ApplicationModelPermissions(DjangoModelPermissions):
    perms_map = {
        'GET': ['%(app_label)s.view_%(model_name)s'],
        'OPTIONS': [],
        'HEAD': [],
        'POST': ['%(app_label)s.add_%(model_name)s'],
        'PUT': ['%(app_label)s.change_%(model_name)s'],
        'PATCH': ['%(app_label)s.change_%(model_name)s'],
        'DELETE': ['%(app_label)s.delete_%(model_name)s'],
    }

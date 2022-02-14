from django.contrib.auth import get_user_model
from rest_framework.exceptions import NotAuthenticated, NotFound

from cozmo_common.permissions import ApplicationModelPermissions, IsOrgAllowedToRead


class ModelPermissionsMixin:
    """Deprecated"""

    def get_permissions(self):
        permissions = super(ModelPermissionsMixin, self).get_permissions()
        permissions.append(IsOrgAllowedToRead())
        return permissions

    def get_object_permissions(self, obj):
        raise NotImplementedError()

    def permission_denied(self, request, message=None):
        """
        Return 404 instead of 403
        """
        if request.authenticators and not request.successful_authenticator:
            raise NotAuthenticated()
        raise NotFound(detail=message)


class ApplicationPermissionViewMixin:
    def get_permissions(self):
        permissions = super(ApplicationPermissionViewMixin, self).get_permissions()
        add_permissions = getattr(self, "add_permissions", list())
        permissions.extend([ApplicationModelPermissions()] + [p() for p in add_permissions])
        return permissions


class ChangedFieldMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initial_data = {}

    def snapshot_data(self):
        self._initial_data = self._as_dict().copy()
        ignored_fields = ("date_updated", "date_created")
        for field in ignored_fields:
            self._initial_data.pop(field, None)

    def _as_dict(self):
        ignored_fields = ("date_updated", "date_created", "_state")
        initial_data = self.__dict__.copy()
        related_objects = self._get_related_objects_for_change_fields()
        data = dict()
        for each in related_objects:
            rel_obj = getattr(self, each, None)
            if not rel_obj:
                continue
            data[each] = rel_obj.__dict__
            for field in ignored_fields:
                data[each].pop(field, None)
        initial_data.update(data)
        return initial_data

    def _get_related_objects_for_change_fields(self):
        return list()

    def _get_nested_changed_related_fields(self, new, old):
        if isinstance(new, dict):
            return {field: value for field, value in new.items() if value != old[field]}
        return new

    def _changed_fields(self):
        d = self._as_dict()
        return {
            field: self._get_nested_changed_related_fields(value, d[field])
            for field, value in self._initial_data.items()
            if value != d[field]
        }

    def _get_nested_updated_related_fields(self, new, old):
        if isinstance(new, dict):
            data = {
                field: {"initial": value, "updated": old[field]}
                for field, value in new.items()
                if value != old[field]
            }
            return data
        return {"initial": new, "updated": old}

    def _updated_fields(self):
        fields = self._changed_fields()
        d = self._as_dict()
        return {
            field: self._get_nested_updated_related_fields(value, d[field])
            for field, value in fields.items()
            if value != d[field]
        }

    @property
    def request_user(self):
        return self._request_user if hasattr(self, "_request_user") else None

    @request_user.setter
    def request_user(self, value):
        self._request_user = value if isinstance(value, get_user_model()) else None

from guardian.shortcuts import get_objects_for_user
from rest_framework.compat import coreapi, coreschema
from rest_framework.filters import BaseFilterBackend

from accounts.models import OrgMembership
from listings.choices import PropertyStatuses
from rental_connections.models import RentalConnection


class GroupFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        group_id = request.query_params.get("group")
        if group_id is not None:
            queryset = queryset.filter(group_id=group_id)
        return queryset

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name="group",
                required=False,
                location="query",
                schema=coreschema.Integer(description="Id of a property group"),
            )
        ]


class PublicApiAccessFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        # temporary hack to allow a user to access all properties via API TODO
        if request.user.is_superuser:
            return queryset.filter(organization__settings__channel_network_enabled=True)
        organization = request.user.organization
        child_orgs = [o.child for o in OrgMembership.objects.filter(parent=organization)]
        cozmo_qs = queryset.filter(rental_connection=None)
        connections_qs = RentalConnection.objects.filter(
            organization__in=[organization] + child_orgs
        )
        perms = {"public_api_access"}
        permitted = get_objects_for_user(
            request.user, perms, connections_qs, with_superuser=False
        ).values_list("id", flat=True)
        imported_qs = queryset.filter(rental_connection__id__in=permitted)
        return cozmo_qs | imported_qs


class FormatFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        return queryset

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name="_format",
                required=False,
                location="query",
                schema=coreschema.String(
                    default="legacy", description="Allow to add additional fields to the response"
                ),
            )
        ]


class LegacyIdFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        legacy_id = request.query_params.get("legacyId")
        if legacy_id is not None:
            queryset = queryset.filter(legacy_id=legacy_id)
        return queryset

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name="legacyId",
                required=False,
                location="query",
                schema=coreschema.String(description="Legacy Id filter"),
            )
        ]


class AllowedStatusFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        return queryset.filter(status=PropertyStatuses.Active)

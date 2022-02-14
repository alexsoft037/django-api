from rest_framework.filters import BaseFilterBackend

from accounts.choices import RoleTypes


class TeamFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        accepted_roles = [
            RoleTypes.owner,
            RoleTypes.admin,
            RoleTypes.contributor,
            RoleTypes.contributor_group,
        ]
        query = {"role__in": [role.value for role in accepted_roles]}

        return queryset.filter(**query)

    # def get_schema_fields(self, view):
    #     return [
    #         coreapi.Field(
    #             name="assignee",
    #             required=False,
    #             location="query",
    #             schema=coreschema.Integer(title="Id of assignee", description="Id of assignee"),
    #         ),
    #     ]

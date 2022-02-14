from rest_framework.compat import coreapi, coreschema
from rest_framework.filters import BaseFilterBackend


class MessageFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        if "conversation_id" in request.query_params:
            queryset = queryset.authorized_messages(
                conversation_id=request.query_params["conversation_id"],
                org_id=request.user.organization
            )

        return queryset

    def get_schema_fields(self, view):
        if view.action == "list":
            return [
                coreapi.Field(
                    name="conversation_id",
                    required=False,
                    location="query",
                    schema=coreschema.Integer(
                        title="Id of a Conversation", description="Id of a Conversation"
                    ),
                )
            ]
        return list()


class ConversationFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        if "reservation_id" in request.query_params:
            queryset = queryset.by_reservation_id(request.query_params["reservation_id"])
        if "owner_id" in request.query_params:
            queryset = queryset.by_owner_id(request.query_params["owner_id"])
        if "org_id" in request.query_params:
            queryset = queryset.by_org_id(request.query_params["org_id"])

        # TODO should we be doing this here or in permissions?
        # return queryset.by_org_id(request.user.organization)
        return queryset

    def get_schema_fields(self, view):
        if view.action == "list":
            return [
                coreapi.Field(
                    name="reservation_id",
                    required=False,
                    location="query",
                    schema=coreschema.Integer(
                        title="Id of a Reservation", description="Id of a Reservation"
                    ),
                ),
                coreapi.Field(
                    name="owner_id",
                    required=False,
                    location="query",
                    schema=coreschema.Integer(
                        title="Id of a Owner", description="Id of a Owner"
                    ),
                ),
                coreapi.Field(
                    name="organization_id",
                    required=False,
                    location="query",
                    schema=coreschema.Integer(
                        title="Id of a Org", description="Id of a Org"
                    ),
                ),
            ]
        return list()

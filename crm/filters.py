from collections import namedtuple
from operator import methodcaller

from rest_framework.compat import coreapi, coreschema
from rest_framework.filters import BaseFilterBackend

from .models import Ticket


class TicketFilter(BaseFilterBackend):

    EnumMapping = namedtuple("EnumMapping", ("choices, field"))

    enum_name_mapping = {
        "status": EnumMapping(choices=Ticket.Statuses, field="status"),
        "type": EnumMapping(choices=Ticket.TicketTypes, field="ticket_type"),
    }

    enum_value_mapping = {"priority": EnumMapping(choices=Ticket.Priorities, field="priority")}

    filter_mapping = {
        "active": methodcaller("active"),
        "archived": methodcaller("archived"),
        "assigned": methodcaller("assigned"),
        "unassigned": methodcaller("unassigned"),
    }

    def filter_queryset(self, request, queryset, view):
        query_params = request.query_params

        filter_method = self.filter_mapping.get(query_params.get("filter"))
        if filter_method:
            queryset = filter_method(queryset)

        kwargs = {}

        if "assignee" in query_params:
            kwargs["assignee"] = (query_params.get("assignee"),)

        if "requester" in query_params:
            kwargs["requester"] = (query_params.get("requester"),)

        for param, mapping in self.enum_value_mapping.items():
            try:
                kwargs[mapping.field] = mapping.choices(int(query_params.get(param, -1)))
            except ValueError:
                continue

        for param, mapping in self.enum_name_mapping.items():
            try:
                kwargs[mapping.field] = mapping.choices[query_params.get(param)]
            except KeyError:
                continue

        return queryset.filter(**kwargs)

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name="assignee",
                required=False,
                location="query",
                schema=coreschema.Integer(title="Id of assignee", description="Id of assignee"),
            ),
            coreapi.Field(
                name="requester",
                required=False,
                location="query",
                schema=coreschema.Integer(title="Id of requester", description="Id of requester"),
            ),
            coreapi.Field(
                name="filter",
                required=False,
                location="query",
                schema=coreschema.Enum(
                    self.filter_mapping.keys(),
                    title="State of tickets",
                    description="State of tickets",
                    default="all",
                ),
            ),
            coreapi.Field(
                name="priority",
                required=False,
                location="query",
                schema=coreschema.Integer(
                    default=Ticket.Priorities.High,
                    title="Priority of tickets",
                    description="Priority of tickets. One of: {}".format(
                        ", ".join(str(p.value) for p in Ticket.Priorities)
                    ),
                ),
            ),
            coreapi.Field(
                name="status",
                required=False,
                location="query",
                schema=coreschema.String(
                    default=Ticket.Statuses.Pending,
                    title="Status of tickets",
                    description="Status of tickets. One of: {}".format(
                        ", ".join(s.name for s in Ticket.Statuses)
                    ),
                ),
            ),
            coreapi.Field(
                name="type",
                required=False,
                location="query",
                schema=coreschema.String(
                    default=Ticket.TicketTypes.Question,
                    description="Type of tickets. One of: {}".format(
                        ", ".join(t.name for t in Ticket.TicketTypes)
                    ),
                ),
            ),
        ]

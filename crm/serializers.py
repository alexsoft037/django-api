from dictdiffer import diff
from rest_framework import serializers

from cozmo_common.fields import DefaultOrganization, NestedRelatedField
from . import fields, models


class ListUpdateSerializer(serializers.ListSerializer):
    def update(self, instances, validated_data):
        for instance, data in zip(instances, validated_data):
            self.child.update(instance, data)
        return instances


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.User
        fields = ("id", "first_name", "last_name", "avatar")


class TicketMinimalSerializer(serializers.ModelSerializer):

    status = fields.EnumField(
        enum_klass=models.Ticket.Statuses, default=models.Ticket.Statuses.Open
    )
    type = fields.EnumField(enum_klass=models.Ticket.TicketTypes, source="ticket_type")

    class Meta:
        model = models.Ticket
        fields = ("id", "title", "type", "status")


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Contact
        exclude = ("organization",)


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.TicketEvent
        fields = ("diff", "date_created")
        ordering = ("-date_created",)


class BulkBaseSerializer(serializers.Serializer):

    tickets = serializers.PrimaryKeyRelatedField(many=True, queryset=models.Ticket.objects.all())

    def validate_tickets(self, tickets):
        organization_id = self.context["request"].user.organization.id
        if any(t for t in tickets if t.organization_id != organization_id):
            raise serializers.ValidationError("Invalid tickets")
        return tickets


class BulkArchiveSerializer(BulkBaseSerializer):
    def create(self, validated_data):
        for ticket in validated_data["tickets"]:
            ticket.is_archived = True
            ticket.save()
        return validated_data


class BulkUpdateSerializer(BulkBaseSerializer):

    status = fields.EnumField(
        enum_klass=models.Ticket.Statuses, default=models.Ticket.Statuses.Open, required=False
    )
    type = fields.EnumField(enum_klass=models.Ticket.TicketTypes, required=False)
    tags = fields.TagRelatedField(many=True, required=False)
    priority = serializers.IntegerField(
        min_value=min(models.Ticket.Priorities),
        max_value=max(models.Ticket.Priorities),
        required=False,
    )
    assignee = NestedRelatedField(
        queryset=models.User.objects.all(),
        serializer=UserSerializer,
        allow_null=True,
        required=False,
    )

    def validate(self, data):
        if "tickets" not in data:
            raise serializers.ValidationError({"tickets": "This field is required"})

        # This will validate status, type, tags and assignee
        serializer = TicketDetailedSerializer(
            instance=data["tickets"][0], data=self.initial_data, partial=True, context=self.context
        )
        serializer.is_valid(raise_exception=True)

        return data

    def create(self, validated_data):
        tickets = validated_data["tickets"]
        serializer = TicketDetailedSerializer(
            instance=tickets,
            partial=True,
            many=True,
            context=self.context,
            data=[self.initial_data] * len(tickets),
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        validated_data.setdefault("assignee", None)
        validated_data.setdefault("tags", [])
        return TicketSerializer(instance=tickets, many=True)


class LinksToSerializer(serializers.ModelSerializer):

    type = fields.EnumField(enum_klass=models.TicketLink.Types, source="link_type")
    ticket = TicketMinimalSerializer(source="to_ticket", read_only=True)

    class Meta:
        model = models.TicketLink
        fields = ("ticket", "type")


class LinkedBySerializer(serializers.ModelSerializer):

    type = fields.EnumField(enum_klass=models.TicketLink.Types, source="link_type")
    ticket = TicketMinimalSerializer(source="from_ticket", read_only=True)

    class Meta:
        model = models.TicketLink
        fields = ("ticket", "type")


class MergeSerializer(BulkBaseSerializer):
    def validate_tickets(self, tickets):
        super().validate_tickets(tickets)
        if self.instance in tickets:
            raise serializers.ValidationError("Cannot merge with itself")
        return tickets

    def update(self, instance, validated_data):
        old = TicketDetailedSerializer(instance=instance).data

        ids = [obj.id for obj in validated_data["tickets"]]
        models.Ticket.objects.filter(id__in=ids).update(status=models.Ticket.Statuses.Solved)

        models.TicketLink.objects.bulk_create(
            models.TicketLink(from_ticket=instance, to_ticket_id=to_id) for to_id in ids
        )

        new = TicketDetailedSerializer(instance=instance).data
        models.TicketEvent.objects.bulk_create(
            models.TicketEvent(diff=d, ticket=instance)
            for d in diff(old, new, ignore=["date_updated"])
        )

        return TicketSerializer(instance=instance)


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Message
        fields = ("text", "author", "date_created", "is_private", "ticket")
        ordering = ("-date_created",)
        extra_kwargs = {
            "date_created": {"read_only": True},
            "author": {"read_only": True},
            "ticket": {"write_only": True},
        }


class StatsSerializer(serializers.Serializer):

    active = serializers.SerializerMethodField()
    assigned = serializers.SerializerMethodField()
    unassigned = serializers.SerializerMethodField()
    archived = serializers.SerializerMethodField()

    def get_active(self, obj):
        return obj.active().count()

    def get_assigned(self, obj):
        return obj.assigned().count()

    def get_unassigned(self, obj):
        return obj.unassigned().count()

    def get_archived(self, obj):
        return obj.archived().count()


class TicketSerializer(TicketMinimalSerializer):

    source = fields.EnumField(enum_klass=models.Ticket.Sources, read_only=True)
    tags = fields.TagRelatedField(many=True, required=False)
    creator = NestedRelatedField(serializer=UserSerializer, read_only=True)
    priority = serializers.IntegerField(
        min_value=min(models.Ticket.Priorities),
        max_value=max(models.Ticket.Priorities),
        required=False,
    )
    assignee = NestedRelatedField(
        queryset=models.User.objects.all(),
        serializer=UserSerializer,
        allow_null=True,
        required=False,
    )
    requester = NestedRelatedField(
        queryset=models.Contact.objects.all(),
        serializer=ContactSerializer,
        allow_null=True,
        required=False,
    )
    organization = serializers.HiddenField(default=DefaultOrganization())

    class Meta:
        model = models.Ticket
        fields = (
            "id",
            "title",
            "summary",
            "date_created",
            "date_updated",
            "type",
            "priority",
            "status",
            "source",
            "tags",
            "creator",
            "assignee",
            "requester",
            "organization",
        )

    def validate_assignee(self, assignee):
        organization_id = self.context["request"].user.organization.id
        if assignee is not None and (
            assignee.organization.id is None or assignee.organization.id != organization_id
        ):
            raise serializers.ValidationError("Choose assignee from your organization")
        return assignee


class TicketDetailedSerializer(TicketSerializer):

    messages = MessageSerializer(many=True, read_only=True)
    events = EventSerializer(many=True, source="ticketevent_set", read_only=True)
    links = LinksToSerializer(many=True, read_only=True)
    linked_by = LinkedBySerializer(many=True, read_only=True)

    class Meta(TicketSerializer.Meta):
        fields = TicketSerializer.Meta.fields + ("events", "messages", "links", "linked_by")
        list_serializer_class = ListUpdateSerializer

    def create(self, validated_data):
        tags = validated_data.pop("tags", [])
        instance = super().create(validated_data)

        for t in tags:
            t.content_object = instance
        instance.tags.bulk_create(tags)

        models.TicketEvent.objects.create(diff=["created", "", []], ticket=instance)

        return instance

    def update(self, instance, validated_data):
        tags = validated_data.pop("tags", None)
        old = TicketDetailedSerializer(instance=instance).data
        instance = super().update(instance, validated_data)

        if tags is not None:
            instance.tags.all().delete()
            for t in tags:
                t.content_object = instance
            instance.tags.bulk_create(tags)

        new = TicketDetailedSerializer(instance=instance).data
        models.TicketEvent.objects.bulk_create(
            models.TicketEvent(diff=d, ticket=instance)
            for d in diff(old, new, ignore=["date_updated"])
        )

        return instance

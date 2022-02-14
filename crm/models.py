from enum import IntEnum

from django.contrib.auth import get_user_model
from django.contrib.contenttypes import fields as ct_fields
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import JSONField
from django.db import models

from cozmo.storages import UploadImageTo
from cozmo_common.db.fields import PhoneField

User = get_user_model()


class Tag(models.Model):

    name = models.CharField(max_length=80)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = ct_fields.GenericForeignKey("content_type", "object_id")


class Contact(models.Model):

    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    secondary_email = models.EmailField(blank=True)
    phone = PhoneField(blank=True)
    secondary_phone = PhoneField(blank=True)
    avatar = models.ImageField(
        upload_to=UploadImageTo("crm/guests"), max_length=500, null=True, blank=True
    )
    location = models.CharField(max_length=150, blank=True)
    note = models.TextField(default="", blank=True)
    external_id = models.CharField(max_length=150, default="")
    organization = models.ForeignKey(
        "accounts.Organization", related_name="+", on_delete=models.CASCADE
    )
    credit_cards = ct_fields.GenericRelation(
        "payments.CreditCard",
        related_query_name="contact",
        content_type_field="content_type",
        object_id_field="customer_obj_id",
    )

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class TicketQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_archived=False)

    def archived(self):
        return self.filter(is_archived=True)

    def assigned(self):
        return self.active().exclude(assignee=None)

    def unassigned(self):
        return self.active().filter(assignee=None)


class Ticket(models.Model):
    class Priorities(IntEnum):
        Low = 1
        Medium = 2
        High = 3
        Urgent = 4

    class TicketTypes(IntEnum):
        Question = 1
        Incident = 2
        Problem = 3
        Task = 4

    class Statuses(IntEnum):
        Open = 0
        Pending = 1
        Solved = 2

    class Sources(IntEnum):
        Manual = 0
        Email = 1

    title = models.CharField(max_length=280)
    summary = models.TextField(default="", blank=True)
    date_created = models.DateTimeField(auto_now_add=True, editable=False)
    date_updated = models.DateTimeField(auto_now=True, editable=False)
    ticket_type = models.SmallIntegerField(choices=tuple((t.value, t.name) for t in TicketTypes))
    priority = models.SmallIntegerField(
        choices=tuple((p.value, p.name) for p in Priorities), default=Priorities.Medium.value
    )
    status = models.SmallIntegerField(
        choices=tuple((s.value, s.name) for s in Statuses), default=Statuses.Open.value
    )
    source = models.SmallIntegerField(
        choices=tuple((s.value, s.name) for s in Sources), default=Sources.Manual.value
    )
    tags = ct_fields.GenericRelation(Tag, related_query_name="tickets")
    is_archived = models.BooleanField(default=False, blank=True)
    assignee = models.ForeignKey(
        User, null=True, blank=True, related_name="tickets_assigned", on_delete=models.SET_NULL
    )
    creator = models.ForeignKey(
        User, null=True, blank=True, related_name="tickets_created", on_delete=models.SET_NULL
    )
    requester = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL)
    organization = models.ForeignKey(
        "accounts.Organization", related_name="+", on_delete=models.CASCADE
    )

    objects = TicketQuerySet.as_manager()

    class Meta:
        indexes = [models.Index(fields=["-date_created", "-priority"])]


class Message(models.Model):

    text = models.TextField()
    author = models.ForeignKey(User, related_name="+", on_delete=models.CASCADE)
    date_created = models.DateTimeField(auto_now_add=True, editable=False)
    date_updated = models.DateTimeField(auto_now=True, editable=False)
    is_private = models.BooleanField(default=False, blank=True)
    ticket = models.ForeignKey(Ticket, related_name="messages", on_delete=models.CASCADE)


class TicketEvent(models.Model):

    diff = JSONField()
    date_created = models.DateTimeField(auto_now_add=True, editable=False)
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE)


class TicketLink(models.Model):
    class Types(IntEnum):
        Link = 1
        Duplicate = 2

    from_ticket = models.ForeignKey(Ticket, related_name="links", on_delete=models.CASCADE)
    to_ticket = models.ForeignKey(Ticket, related_name="linked_by", on_delete=models.CASCADE)
    link_type = models.SmallIntegerField(
        choices=tuple((t.value, t.name) for t in Types), default=Types.Link.value
    )

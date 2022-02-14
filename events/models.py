from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import JSONField
from django.db import models

from .choices import EventType


class Event(models.Model):

    event_type = models.IntegerField(choices=EventType.choices())
    timestamp = models.DateTimeField(auto_now_add=True)
    context = JSONField(default={})
    user = models.ForeignKey(
        get_user_model(), on_delete=models.SET_NULL, related_name="event_logs", null=True
    )
    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, null=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True)
    object_id = models.PositiveIntegerField(null=True)
    content_object = GenericForeignKey("content_type", "object_id")

    class Meta:
        indexes = [models.Index(fields=["timestamp"])]

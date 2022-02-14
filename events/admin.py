from django.contrib import admin

from events.models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    search_fields = ("user__email", "event_type")
    list_display = (
        "user",
        "event_type",
        "content_type",
        "content_object",
        "object_id",
        "context",
        "timestamp",
    )
    list_filter = ("user", "event_type")
    ordering = ("-id",)

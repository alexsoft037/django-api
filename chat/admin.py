from django.contrib import admin

from chat.models import Settings


@admin.register(Settings)
class ChatSettingsAdmin(admin.ModelAdmin):
    search_fields = ("org_settings__organization_id",)
    # list_display = (
    #     "org_settings__organization_id",
    # )
    # list_filter = ("start_date", "end_date", "source", "status")
    fields = (
        "enabled",
        "early_bag_dropoff_enabled",
        "discount_enabled",
        "refund_enabled",
        "early_check_in_enabled",
        "thanks_enabled",
        "distance_enabled",
        "recommendations_enabled",
        "amenities_enabled",
        "wifi_enabled",
        "availability_enabled",
        "late_check_out_enabled",
        "location_enabled",
        "cancellation_enabled",
    )
    ordering = ("-id",)

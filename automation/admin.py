from django.contrib import admin
from django.utils.html import format_html

from automation.models import ReservationMessage
from send_mail.choices import DeliveryStatus

status_to_color = {
    DeliveryStatus.delivered: "#008000",
    DeliveryStatus.failed: "#FF6347",
    DeliveryStatus.not_delivered: "#FF6347",
    DeliveryStatus.started: "#8470ff",
    DeliveryStatus.not_started: "#8470ff",
}

DEFAULT_STATUS_TEXT_COLOR = "#FFFFFF"


@admin.register(ReservationMessage)
class ReservationMessageAdmin(admin.ModelAdmin):
    search_fields = ("event", "reservation_id", "organization_id", "schedule_id", "recipient")

    list_display = (
        "property_address",
        "reservation_check_in",
        # "recipient_name",
        "subject",
        "event",
        # "colored_delivery_status",
        # "date_delivered",
    )
    fields = (
        "id",
        "event",
        "reservation",
        "organization",
        "schedule",
        "message",
        "content",
        "subject",
        "recipient",
    )
    readonly_fields = ("id",)
    ordering = ("-id",)

    def message_status(self, obj):
        return DeliveryStatus(obj.message.delivery_status).name
    message_status.short_description = "Message Status"

    def recipient_name(self, obj):
        return obj.message.recipient
    recipient_name.short_description = "Recipient"

    def reservation_check_in(self, obj):
        return obj.reservation.start_date
    reservation_check_in.short_description = "Check-in"

    def property_address(self, obj):
        return obj.reservation.prop.full_address
    property_address.short_description = "Property Address"

    def colored_delivery_status(self, obj):
        status = DeliveryStatus(obj.message.delivery_status)
        return format_html(
            '<span style="padding: 5px; color: {}; background-color: {};">{}</span>',
            DEFAULT_STATUS_TEXT_COLOR,
            status_to_color.get(status, DEFAULT_STATUS_TEXT_COLOR),
            status.name,
        )

    colored_delivery_status.short_description = "Status"
    colored_delivery_status.admin_order_field = "status"

    def date_delivered(self, obj):
        return obj.message.date_delivered
    date_delivered.short_description = "Date Delivered"

from django.contrib import admin
from django.utils.html import format_html

from listings.choices import ReservationStatuses
from listings.models import (Group, GroupUserAssignment, Property, Reservation,
                             ReservationDiscount, ReservationFee, ReservationRate, ExternalListing)

admin.site.register(Group)
admin.site.register(GroupUserAssignment)

status_to_color = {
    ReservationStatuses.Accepted: "#008000",
    ReservationStatuses.Cancelled: "#FF6347",
    ReservationStatuses.Inquiry: "#8470ff",
    ReservationStatuses.Inquiry_Blocked: "#8470ff",
}

WHITE = "#FFFFFF"


class FeeInline(admin.TabularInline):
    model = ReservationFee


class DiscountInline(admin.TabularInline):
    model = ReservationDiscount


class RateInline(admin.TabularInline):
    model = ReservationRate


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    search_fields = (
        "confirmation_code",
        "id",
        "prop__name",
        "price",
        "guest__first_name",
        "guest__last_name",
        "guest__email",
        "guest__phone",
    )
    list_display = (
        "confirmation_code",
        "id",
        "start_date",
        "end_date",
        "guest_full_name",
        "colored_status",
        "source",
        "external_id",
        "prop_id",
        "property_name",
        "price",
    )
    list_filter = ("start_date", "end_date", "source", "status")
    fields = (
        "property_name",
        "confirmation_code",
        "id",
        "start_date",
        "end_date",
        "guest_full_name",
        "guest",
        "status",
        "guests_adults",
        "guests_children",
        "guests_infants",
        "pets",
        "prop",
        "external_id",
        "cancellation_policy",
        "base_total",
        "paid",
        "rebook_allowed_if_cancelled",
    )
    readonly_fields = ("property_name", "confirmation_code", "guest_full_name", "id")
    inlines = (RateInline, FeeInline, DiscountInline)
    ordering = ("-id",)

    def colored_status(self, obj):
        status = ReservationStatuses(obj.status)
        return format_html(
            '<span style="padding: 5px; color: {}; background-color: {};">{}</span>',
            WHITE,
            status_to_color.get(status, WHITE),
            status.name,
        )

    colored_status.short_description = "Status"
    colored_status.admin_order_field = "status"

    def guest_full_name(self, obj):
        return " ".join([obj.guest.first_name, obj.guest.last_name])

    guest_full_name.short_description = "Guest Name"

    def property_name(self, obj):
        return obj.prop.name

    property_name.short_description = "Property Name"
    property_name.admin_order_field = "prop__name"


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    search_fields = ("id", "name", "location__address", "organization__id")
    list_display = (
        "id",
        "name",
        "property_type",
        "bedrooms",
        "bathrooms",
        "owner",
        "organization",
        "full_address",
    )
    fields = (
        "id",
        "name",
        "property_type",
        "bedrooms",
        "bathrooms",
        "owner",
        "organization",
        "group",
    )
    readonly_fields = ("id",)
    ordering = ("-id",)


@admin.register(ExternalListing)
class ExternalListingAdmin(admin.ModelAdmin):
    pass

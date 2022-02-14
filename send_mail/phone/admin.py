from django.contrib import admin

from send_mail.phone.models import Number


@admin.register(Number)
class PhoneAdmin(admin.ModelAdmin):
    search_fields = (
        "msisdn",
        "organization__id",
    )
    list_display = (
        "msisdn",
        "country_code",
        "source",
        "capabilities",
        "number_type",
        "active",
        "organization_id",
    )
    list_filter = (
        "source",
    )
    fields = (
        "msisdn",
        "country_code",
        "source",
        "capabilities",
        "number_type",
        "active",
        "organization",
    )

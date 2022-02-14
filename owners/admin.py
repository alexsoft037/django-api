from django.contrib import admin

from accounts.models import OwnerUser


@admin.register(OwnerUser)
class OwnerAdmin(admin.ModelAdmin):
    search_fields = (
        "first_name",
        "last_name",
        "middle_name"
    )
    list_display = (
        "first_name",
        "last_name",
        "middle_name",
        "email",
        "phone",
        "id",
        "num_properties"
    )
    fields = (
        "id",
        "first_name",
        "middle_name",
        "last_name",
        "username",
        "email",
        "phone",
        "account_type"
    )
    readonly_fields = (
        "id",
    )
    ordering = ("-id",)

    def get_form(self, request, obj=None, **kwargs):
        form = super(OwnerAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields["account_type"].initial = "OW"
        return form

    def full_name(self, obj):
        return " ".join([obj.first_name, obj.middle_name, obj.guest.last_name])
    full_name.short_description = "Owner Name"
    full_name.admin_order_field = "first_name"

    def num_properties(self, obj):
        return obj.property_set.count()
    num_properties.short_description = "Property Count"

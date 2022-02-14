from django.conf.urls import url
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html

from send_mail.choices import Status
from send_mail.models import ParseEmailTask
from send_mail.tasks import parse_email


@admin.register(ParseEmailTask)
class ParseEmailTaskAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "sender",
        "recipient",
        "subject",
        "status",
        "error",
        "date_updated",
        "content_object",
        "account_actions",
    )
    list_filter = (
        "status",
    )
    fields = (
        "status",
        "data",
        "sender",
        "recipient",
        "subject",
        "error",
        "date_updated",
        "text",
        "html",
    )
    readonly_fields = ("sender", "recipient", "subject", "date_updated", "text", "error", "html")
    list_select_related = ("content_type",)

    def parse_email(self, request, task_id, *args, **kwargs):
        ParseEmailTask.objects.filter(pk=task_id).update(status=Status.init)
        parse_email(task_id)
        return HttpResponseRedirect(reverse("admin:send_mail_parseemailtask_changelist"))

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            url(
                r"^(?P<task_id>.+)/parse-email/$",
                self.admin_site.admin_view(self.parse_email),
                name="parse-email",
            ),
        ]
        return custom_urls + urls

    def account_actions(self, obj):
        return format_html(
            '<a class="button" href="{}">Parse</a>&nbsp;',
            reverse("admin:parse-email", args=[obj.pk]),
        )

    account_actions.short_description = "User Actions"
    account_actions.allow_tags = True

    def sender(self, obj):
        return obj.data.get("from")

    def recipient(self, obj):
        return obj.data.get("to")

    def subject(self, obj):
        return obj.data.get("subject")

    def text(self, obj):
        return obj.data.get("text")

    def html(self, obj):
        return obj.data.get("html")

    sender.short_description = "Sender"
    recipient.short_description = "Recipient"
    subject.short_description = "Subject"
    text.short_description = "Text"
    html.short_description = "HTML"

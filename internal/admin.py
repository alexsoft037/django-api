import json

from django.apps import apps
from django.conf.urls import url
from django.contrib import admin
from django.core.management import call_command
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from six import StringIO

from .models import DBDump


@admin.register(DBDump)
class DBDumpAdmin(admin.ModelAdmin):
    change_list_template = "entities/dumpdb_changelist.html"
    list_display = ("id", "user", "date_updated", "date_created", "list_actions")

    excluded_apps = (
        "auth",
        "admin",
        "internal",
        "account",
        "accounts",
        "sites",
        "contenttypes",
        "socialaccount",
        "guardian",
        "rest_framework_tracking",
        "guardian",
        "sessions",
        "automation",
        "guardian",
        "notifications",
    )

    # Models that are created on Signal can not be dumped
    excluded_apps_for_dumping = excluded_apps + (
        "listings.schedulingassistant",
        "calendars.cozmocalendar",
        "send_mail.welcometemplate",
    )

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            url(r"dump_db/$", self.dump_db),
            url(
                r"^(?P<dbdump_id>.+)/restore/$",
                self.admin_site.admin_view(self.restore),
                name="restore",
            ),
        ]
        return my_urls + urls

    def restore(self, request, dbdump_id, *args, **kwargs):
        for app, models in apps.all_models.items():
            if app in self.excluded_apps:
                continue
            for _, d in models.items():
                d.objects.all().delete()

        obj = self.model.objects.get(pk=dbdump_id)
        call_command("loaddata_str", "-", str=json.dumps(obj.data), format="json")
        url = reverse("admin:internal_dbdump_changelist", current_app=self.admin_site.name)
        return HttpResponseRedirect(url)

    def dump_db(self, request):
        out = StringIO()
        call_command("dumpdata", exclude=self.excluded_apps_for_dumping, format="json", stdout=out)
        out.seek(0)
        self.model.objects.create(user=request.user, data=json.loads(out.read()))
        return HttpResponseRedirect("../")

    def list_actions(self, obj):
        return format_html(
            '<a class="button" href="{}">Restore</a>', reverse("admin:restore", args=[obj.pk])
        )

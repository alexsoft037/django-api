from django.apps import AppConfig


class CalendarsConfig(AppConfig):
    name = "listings.calendars"

    def ready(self):
        from . import signals  # noqa: F401

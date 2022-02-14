from django.apps import AppConfig


class AutomationConfig(AppConfig):
    name = "automation"

    def ready(self):
        from . import signals  # noqa: F401

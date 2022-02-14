from django.apps import AppConfig


class VendorsConfig(AppConfig):
    name = "vendors"

    def ready(self):
        from . import signals  # noqa: F401

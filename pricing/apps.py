from django.apps import AppConfig


class PricingConfig(AppConfig):
    name = "pricing"

    def ready(self):
        from . import signals  # noqa: F401

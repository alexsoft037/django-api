from django.apps import AppConfig


class RentalIntegrationsConfig(AppConfig):
    name = "rental_integrations"

    def ready(self):
        from . import signals  # noqa: F401

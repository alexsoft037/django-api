from django.apps import AppConfig


class AirbnbConfig(AppConfig):
    name = "rental_integrations.airbnb"

    def ready(self):
        from . import signals  # noqa: F401

from django.apps import AppConfig


class RentalNetworkConfig(AppConfig):
    name = "rental_network"

    def ready(self):
        from . import signals  # noqa: F401

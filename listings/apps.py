from django.apps import AppConfig


class ListingsConfig(AppConfig):
    name = "listings"
    verbose_name = "Cozmo Listings"

    def ready(self):
        from . import signals  # noqa: F401

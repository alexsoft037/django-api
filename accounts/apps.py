from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "accounts"
    verbose_name = "Cozmo Accounts"

    def ready(self):
        from . import signals  # noqa: F401

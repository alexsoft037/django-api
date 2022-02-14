from django.apps import AppConfig


class SendMailConfig(AppConfig):
    name = "send_mail"

    def ready(self):
        from . import signals  # noqa: F401

from django.apps import AppConfig


class MessageTemplatesConfig(AppConfig):
    name = "message_templates"

    def ready(self):
        from . import signals  # noqa: F401

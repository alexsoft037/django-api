from django.db import models

from message_templates.choices import TemplateTypes
from message_templates.querysets import TemplateQuerySet


class TemplateManager(models.Manager):

    def get_queryset(self):
        return TemplateQuerySet(self.model, using=self._db)


class SMSMessageManager(TemplateManager):

    def get_queryset(self):
        return super(SMSMessageManager, self).get_queryset().messages()

    def create(self, **kwargs):
        kwargs.update({"template_type": TemplateTypes.Message.value})
        return super(TemplateManager, self).create(**kwargs)


class WelcomeMessageManager(TemplateManager):

    def get_queryset(self):
        return super(WelcomeMessageManager, self).get_queryset().welcome_templates()

    def create(self, **kwargs):
        kwargs.update({"template_type": TemplateTypes.Email.value})
        return super(TemplateManager, self).create(**kwargs)


class MessageManager(TemplateManager):

    def get_queryset(self):
        return super(MessageManager, self).get_queryset().messages()

    def create(self, **kwargs):
        kwargs.update({"template_type": TemplateTypes.Email.value})
        return super(TemplateManager, self).create(**kwargs)

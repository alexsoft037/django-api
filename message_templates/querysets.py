from django.db import models

from message_templates.models import TemplateTypes


class TemplateQuerySet(models.QuerySet):
    def welcome_templates(self):
        return self.filter(template_type=TemplateTypes.Email.value)

    def messages(self):
        return self.filter(template_type=TemplateTypes.email.value)

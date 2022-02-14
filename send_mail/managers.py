from django.db import models

from send_mail.choices import MessageType
from send_mail.querysets import MessageQuerySet


class MessageManager(models.Manager):

    def get_queryset(self):
        return MessageQuerySet(self.model, using=self._db)


class APIMessageManager(MessageManager):

    def get_queryset(self):
        return super(APIMessageManager, self).get_queryset().api_messages()

    def create(self, **kwargs):
        kwargs.update({"type": MessageType.api.value})
        thread_id = kwargs.get("conversation").thread_id
        kwargs.update({"sender": ""})
        kwargs.update({"recipient": thread_id})
        kwargs.update({"recipient_info": thread_id})
        return super(MessageManager, self).create(**kwargs)


class EmailMessageManager(MessageManager):

    def get_queryset(self):
        return super(EmailMessageManager, self).get_queryset().email_messages()

    def create(self, **kwargs):
        kwargs.update({"type": MessageType.email.value})
        return super(MessageManager, self).create(**kwargs)


class ManagedEmailMessageManager(MessageManager):

    def get_queryset(self):
        return super(ManagedEmailMessageManager, self).get_queryset().managed_email_messages()

    def create(self, **kwargs):
        kwargs.update({"type": MessageType.email_managed.value})
        return super(MessageManager, self).create(**kwargs)


class SMSMessageManager(MessageManager):

    def get_queryset(self):
        return super(SMSMessageManager, self).get_queryset().sms_messages()

    def create(self, **kwargs):
        kwargs.update({"type": MessageType.sms.value})
        phone = kwargs.get("recipient")
        kwargs.update({"recipient_info": phone})
        return super(MessageManager, self).create(**kwargs)


class ConversationManager(models.Manager):
    def get_queryset(self):
        return super(ConversationManager, self).get_queryset().authorized_messages()

from django.db import models

from send_mail.choices import MessageType


class MessageQuerySet(models.QuerySet):
    def api_messages(self):
        return self.filter(type=MessageType.api.value)

    def email_messages(self):
        return self.filter(type=MessageType.email.value)

    def managed_email_messages(self):
        return self.filter(type=MessageType.email_managed.value)

    def sms_messages(self):
        return self.filter(type=MessageType.sms.value)

    def by_conversation_id(self, conversation_id):
        return self.filter(conversation_id=conversation_id)

    def by_org_id(self, org_id):
        return self.filter(conversation__reservation__prop__organization_id=org_id)

    def authorized_messages(self, conversation_id, org_id):
        return self.by_conversation_id(conversation_id).by_org_id(org_id)


class ConversationQuerySet(models.QuerySet):
    def by_reservation_id(self, reservation_id):
        return self.filter(reservation_id=reservation_id)

    def by_org_id(self, org_id):
        return self.filter(reservation__prop__organization_id=org_id)

    def by_owner_id(self, owner_id):
        return self.filter(reservation__prop__owner_id=owner_id)

    def authorized_messages(self, reservation_id, org_id):
        return self.by_reservation_id(reservation_id).by_org_id(org_id)

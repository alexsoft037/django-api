from django.db.models import Manager

from rental_integrations.queryset import ChannelSyncQuerySet


class ChannelSyncManager(Manager):
    def get_queryset(self):
        return ChannelSyncQuerySet(self.model, using=self._db)

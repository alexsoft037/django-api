from rental_integrations.airbnb.choices import ChannelType
from rental_integrations.manager import ChannelSyncManager


class AirbnbSyncManager(ChannelSyncManager):
    def get_queryset(self):
        return super(AirbnbSyncManager, self).get_queryset().airbnb()

    def create(self, **kwargs):
        kwargs.update({"channel_type": ChannelType.airbnb.value})
        return super(ChannelSyncManager, self).create(**kwargs)

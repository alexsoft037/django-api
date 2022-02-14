from rental_integrations.airbnb.choices import ChannelType
from rental_integrations.manager import ChannelSyncManager


class TripAdvisorSyncManager(ChannelSyncManager):
    def get_queryset(self):
        return super(TripAdvisorSyncManager, self).get_queryset().tripadvisor()

    def create(self, **kwargs):
        kwargs.update({"channel_type": ChannelType.tripadvisor.value})
        return super(ChannelSyncManager, self).create(**kwargs)

    # def update(self, **kwargs):

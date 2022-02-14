from django.db.models import QuerySet

from rental_integrations.airbnb.choices import ChannelType


class ChannelSyncQuerySet(QuerySet):
    def tripadvisor(self):
        return self.filter(channel_type=ChannelType.tripadvisor.value)

    def airbnb(self):
        return self.filter(channel_type=ChannelType.airbnb.value)

    def bookingcom(self):
        return self.filter(channel_type=ChannelType.bookingcom.value)

    def homeaway(self):
        return self.filter(channel_type=ChannelType.homeaway.value)

    def by_org_id(self, org_id):
        return self.filter(organization_id=org_id)

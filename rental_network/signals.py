import logging
import random

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from listings.models import Property
from rental_network.models import Account, Listing, Proxy, ProxyAssignment, RentalNetworkJob
from rental_network.serializers import (
    CozmoListingToApartmentsSerializer,
    CozmoListingToZillowSerializer,
)
from settings.models import OrganizationSettings

logger = logging.getLogger(__name__)


def _get_proxy():
    return random.choice(Proxy.objects.all())


@receiver(post_save, sender=Property)
def update_rental_network_listing(sender, instance, created, **kwargs):
    # TODO check if listing is valid per account so we can avoid a failed upload
    if (
        instance.channel_network_enabled
        and instance.status == Property.Statuses.Active.value
        and instance.organization.settings.channel_network_enabled
        and settings.LONG_TERM_CHANNELS_ENABLED
    ):
        accounts = Account.objects.filter(organization=instance.organization)
        for account in accounts:
            account_type = account.account_type
            serializer_mapping = {
                Account.AccountType.APARTMENTS.value: CozmoListingToApartmentsSerializer,
                Account.AccountType.ZILLOW.value: CozmoListingToZillowSerializer,
            }
            serializer_class = serializer_mapping.get(account_type)
            if not serializer_class:
                continue
            serializer = serializer_class(data=instance.__dict__)
            if not serializer.is_valid():
                continue

            listing = Listing.objects.filter(account=account, prop=instance).exists()
            proxy_assignment = ProxyAssignment.objects.filter(account=account, prop=instance)
            if not proxy_assignment.exists():
                proxy_assignment = ProxyAssignment.objects.create(
                    account=account, prop=instance, proxy=_get_proxy()
                )
            else:
                proxy_assignment = proxy_assignment[0]
            job_type = (
                RentalNetworkJob.Type.CREATE
                if created or not listing
                else RentalNetworkJob.Type.UPDATE
            )
            RentalNetworkJob.objects.get_or_create(
                status=RentalNetworkJob.Status.INIT,
                job_type=job_type,
                prop=instance,
                proxy=proxy_assignment.proxy,
                account=account,
            )


@receiver(post_save, sender=OrganizationSettings)
def update_org_rental_network_settings(sender, instance, created, **kwargs):
    update_fields = kwargs["update_fields"]
    if (
        update_fields
        and "channel_network_enabled" in update_fields
        and settings.LONG_TERM_CHANNELS_ENABLED
    ):
        for prop in instance.organization.property_set:
            prop.channel_network_enabled = instance.channel_network_enabled
            prop.save()

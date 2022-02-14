from django.db.models import CASCADE, ForeignKey

from rental_integrations.models import BaseAccount, BaseListing


class ExpediaAccount(BaseAccount):
    """Representation of a connected expedia.com account."""

    @property
    def channel_type(self) -> str:
        return "Expedia"


class Listing(BaseListing):
    """Representation of a listing imported from expedia.com."""

    owner = ForeignKey(ExpediaAccount, on_delete=CASCADE)

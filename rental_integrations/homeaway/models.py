from django.contrib.postgres.fields import JSONField
from django.db import models

from rental_integrations.exceptions import ServiceException
from rental_integrations.homeaway.service import HomeAwayService
from rental_integrations.models import BaseAccount, BaseListing


class HomeAwayAccount(BaseAccount):
    data = JSONField(null=True, blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._service = None

    @property
    def service(self):
        """Legacy function."""
        if self._service:
            return self._service

        def service_auth_callback(service):
            # save session info and other stuff
            self.session = service.get_session_info()
            self.save()

        self._service = HomeAwayService(
            username=self.user_id, auth_callback=service_auth_callback, **self.session
        )

        return self._service

    @property
    def channel_type(self) -> str:
        return "HomeAway"

    def update_listings(self, commit=False) -> bool:
        self.listing_set.all().delete()
        try:
            listings_data, _ = self.service.get_host_listings()
        except ServiceException:
            return False
        self.listing_set.bulk_create(Listing(data=data, owner=self) for data in listings_data)
        if commit:
            self.save()
        return True


class Listing(BaseListing):

    owner = models.ForeignKey(HomeAwayAccount, on_delete=models.CASCADE)

    @property
    def name(self):
        return self.data.get("name", None)

    @property
    def image(self):
        try:
            url = self.data["images"][0]["url"]
        except (KeyError, IndexError, TypeError):
            url = None
        return url

    @property
    def address(self):
        return self.data.get("address", None)

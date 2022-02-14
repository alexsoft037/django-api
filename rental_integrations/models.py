from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import JSONField
from django.db import models

from accounts.models import Organization
from rental_integrations.choices import ListingApprovalStatus, ListingStatus, ListingSyncScope

User = get_user_model()


class ExternalPasswordField(models.BinaryField):
    """You remove this, you screw migrations."""


class BaseAccount(models.Model):
    """Abstract account model describing integration with rental service."""

    user_id = models.CharField(max_length=50)
    session = JSONField(blank=True, default={})
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    class Meta:
        abstract = True
        unique_together = ("user_id", "organization")

    @property
    def service(self):
        raise NotImplementedError()

    def update_listings(self, secret=None) -> bool:
        raise NotImplementedError()

    def update_reservations(self, secret=None) -> bool:
        raise NotImplementedError()

    def import_listings(self, ids=None) -> bool:
        raise NotImplementedError()

    def import_reservations(self, ids=None) -> bool:
        raise NotImplementedError()

    def get_listings(self, secret=None) -> bool:
        raise NotImplementedError()


class BaseListing(models.Model):
    data = JSONField(null=True, blank=True)
    owner = models.ForeignKey(BaseAccount, on_delete=models.CASCADE)

    class Meta:
        abstract = True

    @property
    def external_id(self) -> str:
        raise NotImplementedError()

    @property
    def name(self) -> str:
        raise NotImplementedError()

    @property
    def image(self) -> str:
        raise NotImplementedError()

    @property
    def address(self) -> str:
        raise NotImplementedError()

    @property
    def channel_type(self) -> str:
        raise NotImplementedError()


class IntegrationSetting(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    channel_type = models.CharField(max_length=25)
    sync = models.BooleanField(default=False)

    class Meta:
        unique_together = ("channel_type", "organization")


class RawResponse(models.Model):
    content = models.BinaryField()
    user = models.CharField(max_length=150)
    date = models.DateTimeField(auto_now_add=True)


class ChannelSync(models.Model):
    """
    Describes a connection between a property listing and a channel listing
    """

    external_id = models.CharField(max_length=255, null=True, blank=True, default="")
    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE)
    sync_enabled = models.BooleanField(default=False)
    auto_push_enabled = models.BooleanField(default=True)

    last_sync = models.DateTimeField(null=True, blank=True)
    date_updated = models.DateTimeField(auto_now=True, null=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    status = models.PositiveSmallIntegerField(
        choices=ListingStatus.choices(), default=ListingStatus.init
    )
    approval_status = models.PositiveSmallIntegerField(
        choices=ListingApprovalStatus.choices(), default=ListingApprovalStatus.not_ready
    )
    scope = models.PositiveSmallIntegerField(
        choices=ListingSyncScope.choices(), default=ListingSyncScope.sync_undecided
    )

    url = models.URLField(blank=True, null=True, default=None)

    class Meta:
        abstract = True

    @property
    def name(self):
        assert self.name, "Name must be implemented"
        return self.name

    # def get_info(self):
    #     raise NotImplementedError("get_info must be implemented")

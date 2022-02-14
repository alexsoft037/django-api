import base64
from enum import auto

from django.core.files.base import ContentFile
from django.db import models

from accounts.models import Organization
from cozmo.storages import UploadImageTo
from cozmo_common.db.models import TimestampModel
from cozmo_common.enums import IntChoicesEnum
from listings.models import Property


class Account(TimestampModel):
    class AccountType(IntChoicesEnum):
        ZILLOW = auto()
        APARTMENTS = auto()

    class ContactPreference(IntChoicesEnum):
        EMAIL = auto()
        PHONE = auto()
        EMAIL_PHONE = auto()

    username = models.CharField(max_length=64)
    password = models.CharField(max_length=64)
    account_type = models.PositiveSmallIntegerField(choices=AccountType.choices())
    contact_first_name = models.CharField(max_length=64)
    contact_last_name = models.CharField(max_length=64)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=16)
    contact_preference = models.PositiveSmallIntegerField(choices=ContactPreference.choices())
    two_factor_phone = models.CharField(max_length=16)
    last_verification_code = models.CharField(max_length=16, blank=True, null=True)
    organization = models.ForeignKey(Organization, null=True, on_delete=models.SET_NULL)

    @property
    def contact_full_name(self):
        names = list(filter(lambda x: x, [self.contact_first_name, self.contact_last_name]))
        return " ".join(names)


class Proxy(TimestampModel):
    username = models.CharField(max_length=64, blank=True)
    password = models.CharField(max_length=64, blank=True)
    host = models.CharField(max_length=512)
    port = models.CharField(max_length=16)

    @property
    def url(self):
        return f"{self.host}:{self.port}"


class ProxyAssignment(TimestampModel):
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    prop = models.ForeignKey("listings.Property", on_delete=models.CASCADE)
    proxy = models.ForeignKey(Proxy, on_delete=models.CASCADE)


class RentalNetworkJob(TimestampModel):
    class Status(IntChoicesEnum):
        INIT = 0
        STARTED = 1
        PAUSED = 2
        ERROR = 3
        STOPPED = 4
        COMPLETED = 5
        CANCELLED = 6

    class Type(IntChoicesEnum):
        CREATE = 1
        UPDATE = 2
        DELETE = 3

    prop = models.ForeignKey(
        "listings.Property", on_delete=models.CASCADE, related_name="rental_network_jobs"
    )
    status = models.PositiveSmallIntegerField(choices=Status.choices(), default=Status.INIT.value)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    proxy = models.ForeignKey(Proxy, on_delete=models.CASCADE)
    step = models.CharField(max_length=36)
    job_type = models.PositiveSmallIntegerField(choices=Type.choices())


class Base64ImageField(models.ImageField):
    def from_native(self, data):
        if isinstance(data, str) and data.startswith("data:image"):
            format, imgstr = data.split(";base54,")
            ext = format.split("/")[-1]

            data = ContentFile(base64.b64decode(imgstr), name="temp." + ext)
        return super(Base64ImageField, self).from_native(data)


class Screenshot(TimestampModel):
    image = models.ImageField(upload_to=UploadImageTo("selenium/images"), blank=True, null=True)
    caption = models.TextField(blank=True, default="")
    job = models.ForeignKey(RentalNetworkJob, on_delete=models.CASCADE)


class Listing(TimestampModel):
    class Status(IntChoicesEnum):
        INIT = 1
        UPLOADING = 2
        UPDATING = 3
        SUBMITTED = 4
        LIVE = 5
        ERROR = 6
        DELISTED = 7
        DELETED = 8

    class Type(IntChoicesEnum):
        ZILLOW = 1
        APARTMENTS = 2

    prop = models.ForeignKey(Property, on_delete=models.CASCADE)
    external_id = models.CharField(max_length=128, blank=True, null=True, default="")
    status = models.PositiveSmallIntegerField(choices=Status.choices(), default=Status.INIT)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    listing_type = models.PositiveSmallIntegerField(choices=Type.choices())
    account = models.ForeignKey(Account, on_delete=models.CASCADE)


class LongTermRentalSettings(TimestampModel):
    lease_duration = models.IntegerField(choices=list(), null=True, default=None)
    date_available = models.DateField(null=True, default=None)
    lease_terms = models.TextField(blank=True, default="")
    prop = models.OneToOneField(
        Property, on_delete=models.CASCADE, null=True, related_name="long_term_rental_settings"
    )

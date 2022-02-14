import logging

from django.contrib.auth import get_user_model
from django.core.files.storage import get_storage_class
from django.db import models

from accounts.models import Organization, OwnerUser
from cozmo_common.db.models import TimestampModel
from cozmo_common.enums import ChoicesEnum

logger = logging.getLogger(__name__)

User = get_user_model()
StorageBackend = get_storage_class()


class Owner(TimestampModel):
    """Property Group"""

    user = models.OneToOneField(OwnerUser, on_delete=models.CASCADE, related_name="owner")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    notes = models.TextField(blank=True, null=True, default="")

    class Meta:
        permissions = (("view_owner", "Can view owners"),)


class Contract(TimestampModel):

    class ContractType(ChoicesEnum):
        EliteVR = "ELT"
        StandardVR = "STD"
        RevenueShare = "RVS"
        Other = "OTR"

    class BillingType(ChoicesEnum):
        Legacy = "LEG"
        Billed = "BLL"
        Company = "COM"
        Other = "OTR"

    owner = models.OneToOneField(Owner, on_delete=models.CASCADE, related_name="contract")
    contract_type = models.CharField(
        choices=ContractType.choices(), max_length=3, null=True, default=None)
    date_signed = models.DateField(null=True, default=None)
    date_listed = models.DateField(null=True, default=None)
    commission = models.IntegerField(null=True, default=None)
    billing_type = models.CharField(
        choices=BillingType.choices(), max_length=3, null=True, default=None)

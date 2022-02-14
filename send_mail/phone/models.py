from django.db import models

from cozmo_common.db.models import TimestampModel


class Number(TimestampModel):

    msisdn = models.CharField(max_length=16, unique=True)
    country_code = models.CharField(max_length=2, default="")
    source = models.CharField(max_length=16, default="")
    capabilities = models.CharField(max_length=32, default="")
    number_type = models.CharField(max_length=16, default="")
    active = models.BooleanField(default=False)
    organization = models.ForeignKey(
        "accounts.Organization", related_name="+", on_delete=models.CASCADE
    )

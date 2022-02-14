from datetime import timedelta
from functools import partial

from django.core.files.storage import get_storage_class
from django.db import models
from drf_extra_fields.fields import DateRangeField as _DateRangeField
from rest_framework.fields import DateField, URLField

from cozmo_common.validators import HourValidator

FalseBooleanField = partial(models.BooleanField, default=False)

PhoneField = models.CharField  # For old migrations


class HourField(models.CharField):
    """Database field for storing hour information in 24 hour format."""

    def __init__(self, *args, **kwargs):
        kwargs["max_length"] = 5
        super().__init__(*args, **kwargs)
        self.validators.append(HourValidator())


class DateRangeField(_DateRangeField):

    child = DateField(allow_null=True)

    def get_value(self, data):
        value = super().get_value(data)
        if isinstance(value, dict):
            value.setdefault("bounds", "[]")
        return value

    def to_representation(self, value):
        if not (value.upper_inc or value.upper_inf or value.isempty):
            value._upper -= timedelta(days=1)
            value._bounds = "[]"
        return super().to_representation(value)


class StorageUrlField(URLField):

    StorageBackend = get_storage_class()

    def to_representation(self, value):
        s = str(value)
        url = self.StorageBackend().url(s) if s else ""
        return super().to_representation(url)

from django.db.models.fields import CharField

from ..validators import PhoneValidator


class PhoneField(CharField):
    """Field for storing phone number in E.164 standard."""

    description = "Phone number"

    def __init__(self, *args, **kwargs):
        kwargs["max_length"] = 16
        super().__init__(*args, **kwargs)
        self.validators.append(PhoneValidator())

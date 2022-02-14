from functools import partial

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator


class HourValidator:
    """Validator to ensure hour in HH:MM format."""

    messages = {
        "format": "Time format should be HH:MM",
        "value": "Invalid %(name)s. Choose between 00 and %(max)s",
    }

    def __call__(self, value):
        if len(value) != 5:
            raise ValidationError(self.messages["format"], code="format")

        try:
            hour, minutes = map(int, value.split(":"))
        except ValueError:
            raise ValidationError(self.messages["format"], code="format")

        if not (0 <= hour < 24):
            raise ValidationError(
                self.messages["value"], code="value", params={"name": "hour", "max": "23"}
            )

        if not (0 <= minutes < 60):
            raise ValidationError(
                self.messages["value"], code="value", params={"name": "hour", "max": "59"}
            )


PhoneValidator = partial(RegexValidator, regex=r"^\+?[1-9]\d{4,14}$")

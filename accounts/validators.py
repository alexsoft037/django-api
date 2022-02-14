from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class OneDigitPasswordValidator:
    """
    Validate whether the password contain one digit.
    """

    def validate(self, password, user=None):
        if not any(char.isdigit() for char in password):
            raise ValidationError(
                _("Password must contain one digit."), code="password_does_not_contain_digit"
            )

    def get_help_text(self):
        return _("Your password must contain one digit.")


class OneUpperPasswordValidator:
    """
    Validate whether the password contain one uppercase.
    """

    def validate(self, password, user=None):
        if not any(char.isupper() for char in password):
            raise ValidationError(
                _("Password must contain one uppercase."),
                code="password_does_not_contain_uppercase",
            )

    def get_help_text(self):
        return _("Your password must contain one uppercase.")


class OneLowerPasswordValidator:
    """
    Validate whether the password contain one lowercase.
    """

    def validate(self, password, user=None):
        if not any(char.islower() for char in password):
            raise ValidationError(
                _("Password must contain one lowercase."),
                code="password_does_not_contain_lowercase",
            )

    def get_help_text(self):
        return _("Your password must contain one lowercase.")

import logging

from rest_framework.exceptions import ValidationError

logger = logging.getLogger(__name__)


class NoRecipientAddressValidationError(ValidationError):
    def __init__(self):
        super().__init__("Recipient must not be null with recipient_type == email")

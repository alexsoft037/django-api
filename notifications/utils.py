import logging

from phonenumbers import PhoneNumberFormat, format_number, parse

logger = logging.getLogger(__name__)


def to_e164(number):
    logger.debug("converting number to to_e164: " + number)
    phone = parse(number, "US")
    return format_number(phone, PhoneNumberFormat.E164)

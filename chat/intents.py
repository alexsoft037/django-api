import logging
from enum import Enum

logger = logging.getLogger(__name__)


class Intent(Enum):
    DISCOUNT = "inquiry.discount"
    REFUND = "inquiry.refunds"
    EARLY_BAG_DROPOFF = "inquiry.early-bag-dropoff"
    EARLY_CHECKIN = "inquiry.early-check-in"
    THANKS = "message.thanks"
    DISTANCE = "inquiry.distance"
    RECOMMENDATIONS = "inquiry.recommendations"
    AMENITIES = "faq.amenities"
    WIFI = "faq.wifi"
    PETS = "inquiry.pets"
    INQUIRY_AVAILABILITY = "inquiry.available"
    HELLO = "inquiry.hello"
    LATE_CHECK_OUT = "inquiry.late-check-out"
    LOCATION = "inquiry.location"
    MORE_INFO = "inquiry.need-more-info"
    NOT_RECEIVED_REFUND = "inquiry.not-received-refund"
    CANCELLATION = "message.cancellation"
    CONTACT_INFO = "message.contact"

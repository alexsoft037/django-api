from enum import Enum


class ApprovalNotes(Enum):
    not_enough_photos = "The listing does not have enough photos. The minimum is 7 photos."
    not_enough_amenities = "The listing does not have enough amenities. \
                            The minimum is 5 amenities."
    not_enough_hd_photos = "The listing has less than 3 high quality photos. High quality photos \
                            should be at least 800 pixels in width, 500 pixels in height."
    not_enough_description = "The listing description is too short. The minimum is 50 characters."
    no_permit = ""  # todo


MIN_PHOTOS = 7
MIN_AMENITIES = 5
MIN_HD_PHOTOS_WIDTH_PX = 800
MIN_HD_PHOTOS_HEIGHT_PX = 500
MIN_DESCRIPTION = 50
MIN_HD_PHOTOS = 3
MAX_PHOTOS = 200
DEFAULT_LOCALE = "en"

LISTING_URL_TEMPLATE = "https://www.airbnb.com/rooms/{}"

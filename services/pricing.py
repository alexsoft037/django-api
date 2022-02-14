import logging
from datetime import date, datetime

logger = logging.getLogger(__name__)

PRICES = {
    "2019": {
        "08": [
            126,
            115,
            119,
            130,
            118,
            131,
            135,
            133,
            131,
            134,
            121,
            121,
            121,
            130,
            115,
            126,
            135,
            127,
            128,
            123,
            121,
            128,
            119,
            135,
            134,
            121,
            120,
            123,
            125,
            127,
            125,
        ],
        "09": [
            119,
            128,
            119,
            120,
            133,
            119,
            128,
            121,
            117,
            132,
            132,
            135,
            118,
            133,
            117,
            121,
            132,
            130,
            116,
            134,
            122,
            133,
            116,
            130,
            123,
            124,
            125,
            130,
            132,
            117,
        ],
        "10": [
            133,
            121,
            128,
            120,
            133,
            132,
            135,
            116,
            126,
            124,
            130,
            118,
            129,
            124,
            134,
            135,
            117,
            128,
            116,
            116,
            115,
            117,
            130,
            124,
            134,
            126,
            130,
            124,
            131,
            123,
            121,
        ],
        "11": [
            117,
            130,
            124,
            134,
            126,
            130,
            124,
            131,
            123,
            121,
            134,
            126,
            130,
            124,
            131,
            123,
            121,
            250,
            270,
            289,
            289,
            270,
            200,
            120,
            120,
            121,
            119,
            98,
            101,
            105,
        ],
        "12": [
            117,
            124,
            131,
            118,
            127,
            116,
            135,
            135,
            121,
            120,
            126,
            116,
            134,
            134,
            117,
            119,
            115,
            128,
            115,
            126,
            131,
            131,
            129,
            134,
            135,
            117,
            135,
            127,
            127,
            120,
            133,
        ],
    }
}


class PricingService:
    """
    Pricing factors
    - Property attributes
        - location
        - ba/br
        - amenities
        - design/furniture
        - floor
        - sqft
        -
    """

    def __init__(self, prop):
        self.prop = prop

    def get_price(self, d):
        """

        :param date:
        :return:
        - reasons dict
        - price
        """
        if isinstance(d, str):
            d = datetime.strptime(d, "%Y-%m-%d").date()
        if isinstance(d, date):
            year, month, day = d.strftime("%Y-%m-%d").split("-")
            try:
                return PRICES[year][month][int(day)]
            except KeyError:
                return 100
        else:
            # raise Exception("Price not found")
            return 100

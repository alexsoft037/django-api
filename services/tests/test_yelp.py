from unittest import mock

from django.test import TestCase

from services.errors import ServiceError
from services.yelp import YelpService

LAT = 32.012343
LNG = -121.034433
NAME = "NAME"
URL = "URL"
RATING = 5.0
CATEGORIES = ["CATE1", "CATE2"]
PHONE = "PHONE"
ADDRESS = "DISPLAY_ADDR"
DISTANCE = 1337.13

YELP_RESPONSE = {
    "businesses": [
        {
            "id": "jlayThZMxwJSmPXEzIFRnQ",
            "alias": "strawberry-hill-san-francisco",
            "name": NAME,
            "image_url": "https://s3-media2.fl.yelpcdn.com/bphoto/pw0sYqRwFxA_cqb2ODkO2Q/o.jpg",
            "is_closed": False,
            "url": URL,
            "review_count": 79,
            "categories": [
                {"alias": CATEGORIES[0], "title": "Parks"},
                {"alias": CATEGORIES[1], "title": "Hiking"},
            ],
            "rating": RATING,
            "coordinates": {"latitude": 37.7686793176374, "longitude": -122.475618124008},
            "transactions": [],
            "location": {
                "address1": "50 Stow Lake Dr",
                "address2": "",
                "address3": "Golden Gate Park",
                "city": "San Francisco",
                "zip_code": "94159",
                "country": "US",
                "state": "CA",
                "display_address": [ADDRESS, "Golden Gate Park", "San Francisco, CA 94159"],
            },
            "phone": PHONE,
            "display_phone": "",
            "distance": DISTANCE,
        }
    ],
    "total": 160,
    "region": {"center": {"longitude": -122.406354, "latitude": 37.780658}},
}


@mock.patch("services.yelp.settings", return_value=mock.MagicMock())
@mock.patch("services.yelp.requests", return_value=mock.MagicMock())
class YelpServiceTest(TestCase):
    def _get_service(self):
        return YelpService()

    def test_result_expected(self, request_mock, settings_mock):
        """
        Tests for expected result
        """
        request_mock.get.return_value.ok = True
        request_mock.get.return_value.json.return_value = YELP_RESPONSE
        service = self._get_service()
        result = service.get_recommendations(LAT, LNG)
        expected = [
            {
                "categories": CATEGORIES,
                "rating": RATING,
                "name": NAME,
                "url": URL,
                "distance": DISTANCE,
                "phone": PHONE,
                "address": ADDRESS,
            }
        ]
        self.assertDictEqual(
            result,
            {
                "restaurants": expected,
                "hiking": expected,
                "pubs": expected,
                "nightlife": expected,
                "coffee": expected,
            },
        )
        self.assertEquals(request_mock.get.call_count, 5)

    def test_error(self, request_mock, settings_mock):
        request_mock.get.return_value.ok = False
        service = self._get_service()
        with self.assertRaises(ServiceError):
            service.get_recommendations(LAT, LNG)
            request_mock.get.assert_called_once()

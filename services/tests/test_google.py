from unittest import mock

from django.test import TestCase

from services.errors import ServiceError
from services.google import GoogleService

TIMEZONE_ID = "TEST_TIMEZONE"
API_KEY = "API_KEY"
LAT = 32.012343
LNG = -121.034433

DEST = "DEST"
ORIGIN = "ORIGIN"
DRIVING_DISTANCE = "1337"
DRIVING_TIME = "1234"
DISTANCE_POSITIVE_RESPONSE = {
    "status": "OK",
    "destination_addresses": [DEST],
    "origin_addresses": [ORIGIN],
    "rows": [
        {
            "elements": [
                {"duration": {"text": DRIVING_TIME}, "distance": {"text": DRIVING_DISTANCE}}
            ]
        }
    ],
}
DISTANCE_NEGATIVE_RESPONSE = {
    "status": "SOMETHING_OTHER_THAN_OK"
}


@mock.patch("services.google.settings", return_value=mock.MagicMock())
@mock.patch("services.google.googlemaps", return_value=mock.MagicMock())
class GoogleServiceTest(TestCase):
    def _get_service(self):
        return GoogleService()

    def test_get_distance_expected(self, gm_mock, settings_mock):
        dist_mock = mock.MagicMock()
        dist_mock.distance_matrix.return_value = DISTANCE_POSITIVE_RESPONSE
        gm_mock.Client.return_value = dist_mock
        service = self._get_service()
        result = service.get_distance_by_address(ORIGIN, DEST)
        self.assertDictEqual(result, {
            "destination": DEST,
            "origin": ORIGIN,
            "driving_distance": DRIVING_DISTANCE,
            "driving_time": DRIVING_TIME
        })
        service.client.distance_matrix.assert_called_once()
        service.client.distance_matrix.assert_called_with(
            units="imperial",
            origins=[ORIGIN],
            destinations=[DEST]
        )

    def test_get_distance_error(self, gm_mock, settings_mock):
        dist_mock = mock.MagicMock()
        dist_mock.distance_matrix.return_value = DISTANCE_NEGATIVE_RESPONSE
        gm_mock.Client.return_value = dist_mock
        service = self._get_service()
        with self.assertRaises(ServiceError):
            service.get_distance_by_address(ORIGIN, DEST)
            service.client.distance_matrix.assert_called_once()
            service.client.distance_matrix.assert_called_with(
                units="imperial",
                origins=[ORIGIN],
                destinations=[DEST]
            )

    def test_timezone_expected(self, gm_mock, settings_mock):
        """
        Tests for expected result
        """
        tz_mock = mock.MagicMock()
        tz_mock.timezone.return_value = {
            "dstOffset": 3600,
            "rawOffset": -28800,
            "status": "OK",
            "timeZoneId": TIMEZONE_ID,
            "timeZoneName": "Pacific Daylight Time",
        }
        gm_mock.Client.return_value = tz_mock
        service = self._get_service()
        result = service.get_timezone(LAT, LNG)
        self.assertEquals(result, TIMEZONE_ID)
        service.client.timezone.assert_called_once()
        service.client.timezone.assert_called_with((LAT, LNG))

    def test_timezone_bad_input(self, gm_mock, settings_mock):
        """
        Tests for incorrect input (i.e. None)
        """
        service = self._get_service()
        with self.assertRaises(AssertionError):
            service.get_timezone(None, None)
            service.client.timezone.assert_not_called()

    def test_timezone_not_ok(self, gm_mock, settings_mock):
        """
        Tests that ServiceError is thrown when Google returns no result that is not "OK".
        :param gm_mock:
        :param settings_mock:
        :return:
        """
        tz_mock = mock.MagicMock()
        tz_mock.timezone.return_value = {"status": "SOMETHING_NOT_OK"}
        gm_mock.Client.return_value = tz_mock

        service = self._get_service()
        with self.assertRaises(ServiceError):
            service.get_timezone(LAT, LNG)
            service.client.timezone.assert_called_once()
            service.client.timezone.assert_called_with((LAT, LNG))

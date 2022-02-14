from unittest import mock
from unittest.mock import MagicMock

from django.test import TestCase

from listings.models import Reservation
from notifications.services.slack import SlackMessageBuilder


class SlackMessageBuilderTest(TestCase):
    def test_get_field(self):
        builder = SlackMessageBuilder()
        title = "TITLE"
        value = "VALUE"
        short = True

        with self.subTest("Valid _get_field result with defaults"):
            result = builder._get_field(title, value)
            self.assertDictEqual(result, {"title": title, "value": f"`{value}`", "short": False})

        with self.subTest("Valid _get_field result"):
            result = builder._get_field(title, value, short)
            self.assertDictEqual(result, {"title": title, "value": f"`{value}`", "short": True})

    @mock.patch("notifications.services.slack.settings.COZMO_WEB_URL")
    def test_get_message(self, mock_settings):
        url = "https://url.com"
        confirmation_code = "abc123"
        start_date = "2020-02-02"
        end_date = "2020-02-20"
        status = 2
        reservation_id = 0
        address = "123 Fake St"
        prop_id = 123

        mock_settings.return_value = url

        mock_reservation = MagicMock(spec=Reservation)
        mock_reservation.confirmation_code = confirmation_code
        mock_reservation.start_date = start_date
        mock_reservation.end_date = end_date
        mock_reservation.pk = reservation_id
        mock_reservation.status = status
        mock_reservation.prop.full_address = address
        mock_reservation.prop.pk = prop_id

        with self.subTest("Valid _get_message response"):
            message = SlackMessageBuilder()._get_message()
            self.assertTrue(len(message.keys()) == 1)
            self.assertTrue("attachments" in message)
            attachments = message["attachments"]
            self.assertTrue(isinstance(attachments, list))
            self.assertTrue(len(attachments) == 1)
            self.assertTrue(
                {"markdwn_in", "footer", "footer_icon"}.issubset(set(attachments[0]))
            )

        with self.subTest("Valid reservation_update_message response"):
            message = SlackMessageBuilder().get_reservation_update_message(mock_reservation)
            items = {"fallback": "", "title": "", "title_link": "", "text": "", "fields": ""}
            content = message["attachments"][0]
            self.assertTrue(set(items.keys()).issubset(set(content)))
            self.assertTrue(len(content["fields"]) == 5)

        with self.subTest("Valid reservation_cancellation_message response"):
            message = SlackMessageBuilder().get_reservation_cancellation_message(mock_reservation)
            items = {"fallback": "", "title": "", "title_link": "", "text": "", "fields": ""}
            self.assertTrue(len(message.keys()) == 1)
            self.assertTrue("attachments" in message)
            content = message["attachments"][0]
            self.assertTrue(set(items.keys()).issubset(set(content)))
            self.assertTrue(len(content["fields"]) == 4)

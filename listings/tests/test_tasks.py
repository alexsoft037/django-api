from unittest import mock

from django.test import TestCase
from requests import ConnectTimeout, HTTPError

from listings.models import Image, Property
from listings.tasks import fetch_property_media


class FetchMediaTaskTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.prop = Property.objects.create(
            name="Name",
            property_type=Property.Types.Apartment.value,
            rental_type=Property.Rentals.Private.value,
            status=Property.Statuses.Active.value,
        )
        cls.original_url = "http://example.org/file.jpg"
        cls.image = Image.objects.create(prop=cls.prop, url=cls.original_url)

    @mock.patch("listings.tasks.requests.get")
    def test_fetch_failure(self, m_get):
        for name, error in (
            ("Connection timeout", ConnectTimeout),
            ("Other http error", HTTPError),
        ):
            with self.subTest(name):
                m_get.side_effect = error
                fetch_property_media.s(self.prop.pk).apply()
                self.image.refresh_from_db()
                self.assertEqual(self.image.url, self.original_url)

from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase

from accounts.models import Organization
from listings.models import Blocking, Property
from rental_integrations.exceptions import ServiceException
from . import serializers
from .models import RentalConnection


class RentalConnectionTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create()
        cls.instance = RentalConnection.objects.create(
            api_type=RentalConnection.Types.Isi.value,
            username="username",
            password="password",
            organization=cls.organization,
        )

    def test_get_properties(self):  # FIXME This test tries to connect to Internet
        listings_count = 3
        with self.subTest("service returns listings"), (
            patch.object(self.instance.service, "get_listings_count", return_value=listings_count)
        ):
            serializer = serializers.RentalConnectionSerializer(instance=self.instance)
            data = serializer.data
            self.assertEqual(listings_count, data["properties"])

        with self.subTest("service returns none"), (
            patch.object(self.instance.service, "get_listings", return_value=None)
        ):
            serializer = serializers.RentalConnectionSerializer(instance=self.instance)
            data = serializer.data
            self.assertEqual(0, data["properties"])

        with self.subTest("service raises exception"), (
            patch.object(self.instance.service, "get_listings", side_effect=ServiceException)
        ):
            serializer = serializers.RentalConnectionSerializer(instance=self.instance)
            data = serializer.data
            self.assertEqual(0, data["properties"])

    def test_create_related_models(self):
        prop = Property.objects.create()
        today = date.today()

        old_blockings = Blocking.objects.bulk_create(
            Blocking(
                prop=prop, time_frame=(today - timedelta(days=1 + i), today - timedelta(days=i))
            )
            for i in range(1, 5)
        )
        future_blockings = Blocking.objects.bulk_create(
            Blocking(
                prop=prop, time_frame=(today + timedelta(days=i), today + timedelta(days=i + 1))
            )
            for i in range(1, 5)
        )

        ext_blockings = [
            (today - timedelta(days=2), today - timedelta(days=1)),  # passed blocking, not saving
            (today, today + timedelta(days=1)),  # starts today, saving
            (today + timedelta(days=1), today + timedelta(days=2)),  # future blocking, saving
        ]

        with patch.object(self.instance.service, "get_reservations", return_value=ext_blockings):
            self.instance._create_related_models(prop, {})

        for blocking in old_blockings:
            blocking.refresh_from_db()
            self.assertIsNotNone(blocking.id)

        for blocking in future_blockings:
            self.assertRaises(Blocking.DoesNotExist, blocking.refresh_from_db)

        # we only want to create future blockings, with starting date from today
        kept_blockings = old_blockings + list(
            (start, end) for start, end in ext_blockings if start >= today
        )
        self.assertEqual(prop.blocking_set.count(), len(kept_blockings))
        self.assertFalse(prop.blocking_set.filter(time_frame__fully_lt=(None, today)).exists())

    def test_update_listing(self):
        self.instance.property_set.all().delete()

        listing_data = {
            "external_id": "some-id",
            "name": "Some name",
            "property_type": Property.Types.Cabin.pretty_name,
            "rental_type": Property.Rentals.Private.pretty_name,
        }
        with patch.object(self.instance, "_create_related_models"):
            self.instance._update_listing(listing_data)
            prop_quantity = self.instance.property_set.count()
            self.assertEqual(prop_quantity, 1)

            self.instance._update_listing(listing_data)
            self.assertEqual(prop_quantity, self.instance.property_set.count())

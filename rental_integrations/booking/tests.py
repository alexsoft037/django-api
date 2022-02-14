"""
import datetime as dt
import json
import logging
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from lxml import etree
from rest_framework.exceptions import ValidationError

from accounts.models import Organization
from accounts.profile.models import PlanSettings
from listings import models as listings_models
from rental_integrations.models import IntegrationSetting
from . import models, serializers, service_serializers as srv_serializers, tasks
from .service import BookingParser


# Model tests


class BookingAccountTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create()
        cls.account = models.BookingAccount.objects.create(
            username="spam", organization=cls.organization
        )

    def setUp(self):
        models.Listing.objects.all().delete()

    @classmethod
    def _add_listing(cls, data=None):
        if data is None:
            data = {
                "id": 1,
                "name": "Some name",
                "rates": [{"max_persons": 0}, {"max_persons": 1}],
            }
        cls.account.listing_set.add(models.Listing.objects.create(owner=cls.account, data=data))

    @mock.patch("rental_integrations.booking.models.BookingXmlClient.get_listings")
    def test_update_listings(self, m_listings):
        with self.subTest(msg="Any network error"):
            m_listings.return_value = (300, [])
            self._add_listing()
            old_count = self.account.listing_set.all().count()
            self.assertGreater(old_count, 0)
            self.assertFalse(self.account.update_listings())
            self.assertEqual(self.account.listing_set.all().count(), old_count)

        with self.subTest(msg="Updated successfully"):
            listings_data = [{"new key": "some value"}, {"new key": "other value"}]
            m_listings.reset_mock()
            m_listings.return_value = (200, listings_data)
            self.assertTrue(self.account.update_listings())

            m_listings.assert_called_once()
            self.assertEqual(self.account.listing_set.all().count(), len(listings_data))
            self.assertEqual(
                self.account.listing_set.filter(data__has_key="new key").count(),
                len(listings_data),
            )

    @mock.patch("rental_integrations.booking.models.Property.objects.update_or_create")
    def test_import_listings(self, m_update_create):
        #  with self.subTest(msg="Import only chosen"), (
        #      mock.patch.object(self.account.listing_set, "filter")
        #  ) as m_filter:
        #      m_update_create.reset_mock()
        #      m_update_create.return_value = (mock.Mock(spec=listings_models.Property), False)
        #      self._add_listing()
        #      self.assertGreater(self.account.listing_set.all().count(), 0)
        #      ids = [1, 2, 3]
        #      self.assertTrue(self.account.import_listings(ids=ids))
        #      m_filter.called_once_with(id__in=ids)

        with self.subTest(msg="Import all"), (
            mock.patch("rental_integrations.booking.models.BookingSync.objects.update_or_create")
        ) as m_booking_update_create:
            m_update_create.reset_mock()
            m_update_create.return_value = (mock.Mock(spec=listings_models.Property), True)
            self._add_listing()
            self.assertGreater(self.account.listing_set.all().count(), 0)
            self.assertTrue(self.account.import_listings())
            call_count = self.account.listing_set.all().count()
            self.assertEqual(m_update_create.call_count, call_count)
            self.assertEqual(m_booking_update_create.call_count, call_count)

    def test_import_reservations(self):
        listing = models.Listing.objects.create(
            data={
                "id": "external-id",
                "reservations": [
                    {
                        "status": "confirmed",
                        "roomreservation_id": "that-id",
                        "arrival_date": "2020-10-20",
                        "departure_date": "2020-10-30",
                        "numberofguests": "2",
                        "totalprice": "500",
                        "customer": {"email": "that@example.org"},
                    },
                    {
                        "status": "cancelled",
                        "roomreservation_id": "this-id",
                        "customer": {"email": "this@example.org"},
                    },
                ],
            },
            owner=self.account,
        )
        non_existing = models.Listing.objects.create(
            data={"id": "non-existing-id", "reservation": []}, owner=self.account
        )

        p = listings_models.Property.objects.create(
            external_id=f"{self.account.channel_type}:{listing.external_id}",
            organization=self.organization,
        )

        self.account.import_reservations()

        p.refresh_from_db()
        listing.refresh_from_db()
        non_existing.refresh_from_db()
        self.assertGreater(p.reservation_set.count(), 0)
        self.assertNotIn("reservations", listing.data)
        self.assertNotIn("reservations", non_existing.data)

    @mock.patch("rental_integrations.booking.models.Listing._save_reservation")
    @mock.patch("rental_integrations.booking.models.BookingXmlClient.get_reservations")
    def test_update_reservations(self, m_reservations, m_save_res):
        room_id = "some-room-id"
        valid_reservation = {
            "customer": {
                "first_name": "Boba",
                "last_name": "Fett",
                "email": "bob@example.org",
                "telephone": "+1 123 456 6789",
            },
            "hotel_id": "some-id",
            "status": "new",
            "room": [{"id": room_id, "hotel_id": "some-hotel-id"}],
        }
        m_reservations.return_value = (200, [valid_reservation])

        with self.subTest(msg="Adding reservation to unknown listing"):
            self.account.listing_set.all().delete()
            with self.assertLogs("cozmo", level=logging.WARNING):
                self.account.update_reservations()
            m_save_res.assert_called_once()
            self.assertTrue(self.account.listing_set.filter(data__id=room_id).exists())

        with self.subTest(msg="Adding reservation to already existing listing"):
            m_save_res.reset_mock()
            self.assertTrue(self.account.listing_set.filter(data__id=room_id).exists())
            self.account.update_reservations()
            m_save_res.assert_called_once()
            self.assertEqual(self.account.listing_set.filter(data__id=room_id).count(), 1)

    def test_integration_setting_was_create(self):
        integration_settings_size = IntegrationSetting.objects.filter(
            organization=self.organization, channel_type=self.account.channel_type
        ).count()
        self.assertEqual(integration_settings_size, 1)


class ListingTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        organization = Organization.objects.create()
        booking_user = models.BookingAccount.objects.create(
            organization=organization, username="username"
        )
        cls.listing = models.Listing.objects.create(owner=booking_user, data={})

    def test_save_reservation(self):
        with self.subTest(msg="New reservation"):
            self.listing.refresh_from_db()
            new = {"id": "new-id", "status": "new"}
            self.listing._save_reservation(new)
            self.assertIn(new, self.listing.data["reservations"])

        with self.subTest(msg="Cancelled reservation"):
            self.listing.refresh_from_db()
            cancelled_id = "cancel-id"
            self.listing.data["reservations"] = [{"id": cancelled_id, "status": "new"}]
            cancel = {"id": cancelled_id, "status": "cancelled"}
            self.listing._save_reservation(cancel)
            cancelled = [
                res for res in self.listing.data["reservations"] if res["id"] == cancelled_id
            ]
            self.assertEqual(len(cancelled), 1)

        with self.subTest(msg="Cancelled reservation but no match"):
            self.listing.refresh_from_db()
            cancelled_id = "cancel-id-no-match"
            cancel = {"id": cancelled_id, "status": "cancelled"}
            self.listing._save_reservation(cancel)
            self.assertIn(cancel, self.listing.data["reservations"])

        with self.subTest(msg="Modified reservation"):
            self.listing.refresh_from_db()
            modified_id = "modified-id"
            self.listing.data["reservations"] = [{"id": modified_id, "status": "new"}]
            modify = {"id": modified_id, "status": "modified"}
            self.listing._save_reservation(modify)
            modified = [
                res for res in self.listing.data["reservations"] if res["id"] == modified_id
            ]
            self.assertEqual(len(modified), 1)

        with self.subTest(msg="Modified reservation but no match"):
            self.listing.refresh_from_db()
            modified_id = "modified-id-no-match"
            modify = {"id": modified_id, "status": "modified"}
            self.listing._save_reservation(modify)
            self.assertIn(modify, self.listing.data["reservations"])

    def test_properties(self):
        data = {"id": "some id", "name": "some name"}
        listing = models.Listing(data=data)

        self.assertEqual(listing.external_id, data["id"])
        self.assertEqual(listing.name, data["name"])
        self.assertEqual(listing.image, "")
        self.assertEqual(listing.address, "")


class MergeDictTestCase(TestCase):
    def test_merge_dict(self):
        with self.subTest(msg="Merge to empty dict"):
            to_dict = {}
            from_dict = {"ok": True}

            models.merge_dict(to_dict, from_dict)
            self.assertDictEqual(to_dict, from_dict)

        with self.subTest(msg="Merge empty dict"):
            to_dict = {"ok": True}
            orig = to_dict.copy()
            from_dict = {}

            models.merge_dict(to_dict, from_dict)
            self.assertDictEqual(to_dict, orig)

        with self.subTest(msg="Merge non-empty dicts"):
            old_key = "old"
            new_key = "new"
            to_dict = {old_key: True}
            from_dict = {new_key: "value"}

            models.merge_dict(to_dict, from_dict)
            self.assertEqual(to_dict[new_key], from_dict[new_key])
            self.assertIn(old_key, to_dict)

        with self.subTest(msg="Merge nested dicts"):
            new_nested = {"new": True}
            to_dict = {"nested": {"old": True}}
            from_dict = {"nested": new_nested}

            models.merge_dict(to_dict, from_dict)
            self.assertIn("old", to_dict["nested"])
            self.assertIn("new", to_dict["nested"])


# Serializer tests


class AvailabilityDateSerializer(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.serializer = srv_serializers._AvailabilityDateSerializer()

    def test_validate_from_date(self):
        now = timezone.now().date()

        with self.subTest(msg="Invalid from_date"), self.assertRaises(ValidationError):
            date = now + dt.timedelta(days=365 * 3 + 1)
            self.serializer.validate_from_date(date)

        with self.subTest(msg="Valid from_date"):
            date = now + dt.timedelta(days=365 * 3)
            self.assertEqual(self.serializer.validate_from_date(date), date)

            date = now
            self.assertEqual(self.serializer.validate_from_date(date), date)

    def test_validate_to_date(self):
        now = timezone.now().date()

        with self.subTest(msg="Invalid to_date"), self.assertRaises(ValidationError):
            date = now + dt.timedelta(days=365 * 3 + 1)
            self.serializer.validate_to_date(date)

        with self.subTest(msg="Valid to_date"):
            date = now + dt.timedelta(days=365 * 3)
            self.assertEqual(self.serializer.validate_to_date(date), date)

            date = now
            self.assertEqual(self.serializer.validate_to_date(date), date)

    def test_validate_dates(self):
        now = timezone.now().date()

        with self.subTest(msg="Invalid dates"), self.assertRaises(ValidationError):
            dates = [now + dt.timedelta(days=365 * 3 + i) for i in range(3)]
            self.serializer.validate_dates(dates)

        with self.subTest(msg="Valid dates"):
            dates = [now + dt.timedelta(days=365 * 2 + i) for i in range(5)]
            self.assertListEqual(self.serializer.validate_dates(dates), dates)

    def test_validate(self):
        now = timezone.now().date()

        with self.subTest(msg="dates and from_date"), self.assertRaises(ValidationError):
            self.serializer.validate({"dates": [now], "from_date": now})

        with self.subTest(msg="Nor dates neither from_date"), self.assertRaises(ValidationError):
            self.serializer.validate({})

        with self.subTest(msg="rooms_to_sell and rate_id"), self.assertRaises(ValidationError):
            self.serializer.validate({"from_date": now, "rooms_to_sell": 321, "rate_id": 123})

        with self.subTest(msg="rate_details and no rate_id"), self.assertRaises(ValidationError):
            self.serializer.validate({"from_date": now, "rate_details": {}})

        with self.subTest(msg="from_date and to_date"):
            data = self.serializer.validate(
                {"from_date": now, "to_date": now + dt.timedelta(days=1), "rooms_to_sell": 321}
            )

        with self.subTest(msg="Multiple dates in dates"):
            dates = [now, now + dt.timedelta(days=1)]
            data = self.serializer.validate({"dates": dates, "rooms_to_sell": 321})

            for key in ("value{}".format(i) for i, date in enumerate(dates, 1)):
                self.assertIn(key, data["date_attrs"])

        with self.subTest(msg="Single date in dates"):
            dates = [now]
            data = self.serializer.validate({"dates": dates, "rooms_to_sell": 321})
            self.assertIn("value", data["date_attrs"])


class AvailabilityRateSerializerTestCase(TestCase):
    def test_validate(self):
        serializer = srv_serializers._AvailabilityRateSerializer()

        with self.subTest(msg="min_stay: invalid max_stay"), (self.assertRaises(ValidationError)):
            serializer.validate({"min_stay": 10, "max_stay": 5})

        with self.subTest(msg="min_stay: invalid max_stay_arrival"), (
            self.assertRaises(ValidationError)
        ):
            serializer.validate({"min_stay": 10, "max_stay_arrival": 5})

        with self.subTest(msg="min_stay_arrival: invalid max_stay"), (
            self.assertRaises(ValidationError)
        ):
            serializer.validate({"min_stay_arrival": 10, "max_stay": 5})

        with self.subTest(msg="min_stay_arrival: invalid max_stay_arrival"), (
            self.assertRaises(ValidationError)
        ):
            serializer.validate({"min_stay_arrival": 10, "max_stay_arrival": 5})

        with self.subTest(msg="No min/max stay constraints"):
            self.assertDictEqual(serializer.validate({}), {})


class BookingAccountSerializerTestCase(TestCase):
    @mock.patch(
        "rental_integrations.booking.serializers.serializers.ModelSerializer.create",
        return_value=mock.MagicMock(spec=models.BookingAccount),
    )
    def test_create(self, m_create):
        secret = "some password"
        serializer = serializers.BookingAccountSerializer()
        instance = serializer.create({"username": "spam", "secret": secret})
        m_create.return_value.update_listings.assert_called_once_with(secret)
        self.assertIsInstance(instance, models.BookingAccount)


# tasks tests


class GetJobsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create()
        PlanSettings.objects.create(
            booking_sync=True, organization=cls.organization, team=1, properties=10
        )
        listings_models.Property.objects.create(organization=cls.organization)

    def test_json_serializable(self):
        try:
            for job in tasks.get_jobs(partial=False):
                json.dumps(job)
        except TypeError:
            raise self.failureException(f"Should be JSON-serializable: {job}") from None


# service tests


class BookingParserTest(TestCase):
    def test_to_booking(self):
        with self.subTest("Minimal property"):
            p = listings_models.Property.objects.create()
            parsed = BookingParser.to_booking(p)
            self.assertIsInstance(parsed, etree._Element)

        with self.subTest("Regular property"):
            p = listings_models.Property.objects.create(
                name="Test property",
                bedrooms=3,
                bathrooms=2,
                property_type=listings_models.Property.Types.Barn,
            )
            p.location = listings_models.Location.objects.create(
                country="USA",
                city="Example Town",
                postal_code="ET123123",
                latitude="80.123123123",
                longitude="45.678678",
            )
            p.owner = listings_models.Owner.objects.create(
                first_name="John", last_name="Doe", email="john@example.org", phone="123123123123"
            )
            p.save()
            parsed = BookingParser.to_booking(p)
            self.assertIsInstance(parsed, etree._Element)
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.aggregates import Sum
from django.test import TestCase
from django.utils import timezone
from psycopg2.extras import DateRange
from rest_framework.exceptions import ValidationError

from accounts.models import Organization
from crm.models import Contact
from listings import models, serializers
from listings.choices import CalculationMethod, PropertyTypes, ReservationStatuses

User = get_user_model()


class AmountFormattedSerializerTestCase(TestCase):
    def test_has_two_decimal_places(self):
        serializer = serializers.ValueFormattedSerializer()
        obj = mock.MagicMock(**{"reservation.prop.pricing_settings.currency": "USD"})
        valid_format = "$1.00"
        for value in [1, 1.0, 1.00, 1.000]:
            with self.subTest(value=value):
                obj.value = value
                formatted = serializer.get_value_formatted(obj)
                self.assertCountEqual(formatted, valid_format)


class ImageOrderSerializerTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.prop = models.Property.objects.create(
            name="Name",
            property_type=models.Property.Types.Apartment.value,
            rental_type=models.Property.Rentals.Private.value,
        )
        cls.images = models.Image.objects.bulk_create(
            models.Image(url=url, prop_id=cls.prop.pk, order=i)
            for i, url in enumerate(("http://example.org/1", "http://example.org/2"))
        )

    def test_is_valid_missing_data(self):
        ser = serializers.ImageOrderSerializer(data={})
        self.assertFalse(ser.is_valid())

    def test_is_valid_not_unique(self):
        ser = serializers.ImageOrderSerializer(
            data={"order": [self.images[0].pk, self.images[0].pk]}, prop_id=self.prop.pk
        )
        self.assertFalse(ser.is_valid())
        self.assertIn("order", ser.errors)
        self.assertIn("unique", ser.errors["order"][0])

    def test_is_valid_not_all(self):
        ser = serializers.ImageOrderSerializer(
            data={"order": [self.images[0].pk]}, prop_id=self.prop.pk
        )
        self.assertFalse(ser.is_valid())
        self.assertIn("order", ser.errors)
        self.assertIn("all elements", ser.errors["order"][0])

    def test_is_valid_not_owned(self):
        not_owned = 99
        ser = serializers.ImageOrderSerializer(
            data={"order": [self.images[0].pk, not_owned]}, prop_id=self.prop.pk
        )
        self.assertFalse(ser.is_valid())
        self.assertIn("order", ser.errors)
        self.assertIn("of this property", ser.errors["order"][0])

    def test_is_valid_raises_on_error(self):
        ser = serializers.ImageOrderSerializer(
            data={"order": [self.images[0].pk]}, prop_id=self.prop.pk
        )
        with self.assertRaises(ValidationError):
            ser.is_valid(raise_exception=True)

    def test_is_valid(self):
        ser = serializers.ImageOrderSerializer(
            data={"order": [i.pk for i in self.images]}, prop_id=self.prop.pk
        )
        self.assertTrue(ser.is_valid())

    def test_create(self):
        orig_order = [i.pk for i in self.images]
        ser = serializers.ImageOrderSerializer(
            data={"order": reversed(orig_order)}, prop_id=self.prop.pk
        )
        self.assertTrue(ser.is_valid())
        new_order = ser.save()
        self.assertListEqual(list(reversed(orig_order)), new_order)


class PointOfInterestSerializerTestCase(TestCase):
    def setUp(self):
        self.prop = models.Property.objects.create(
            name="prop",
            property_type=models.Property.Types.Condo.value,
            rental_type=models.Property.Rentals.Private.value,
        )

    def tearDown(self):
        models.PointOfInterest.objects.all().delete()
        self.prop.delete()

    def test_update_not_substitute(self):
        old_lat = "0.1"
        new_lat = "9.9"
        category = "category"
        with mock.patch("pois.models.YelpCategories.get_parent_category", return_value="") as m_pc:
            coords = models.Coordinates.objects.create(latitude=old_lat, longitude="0.2")
            poi = models.PointOfInterest.objects.create(
                name="Name", coordinates=coords, prop=self.prop, category=category
            )
            ser = serializers.PointOfInterestSerializer(
                poi,
                data={"coordinates": {"latitude": new_lat}, "category": category},
                partial=True,
            )
            self.assertTrue(ser.is_valid(), ser.errors)
            ser.save(prop_id=self.prop.pk)
            coords.refresh_from_db()
            self.assertEqual(coords.latitude, Decimal(new_lat))
            m_pc.assert_called_once_with(category)

    def test_create(self):
        lat = "10.02"
        lon = "20.01"
        name = "Some name"
        category = "category"

        with mock.patch("pois.models.YelpCategories.get_parent_category", return_value="") as m_pc:
            ser = serializers.PointOfInterestSerializer(
                data={
                    "name": name,
                    "coordinates": {"longitude": lon, "latitude": lat},
                    "category": category,
                }
            )
            self.assertTrue(ser.is_valid(), ser.errors)
            poi = ser.save(prop_id=self.prop.pk)
            self.assertEqual(poi.name, name)
            self.assertEqual(poi.coordinates.longitude, Decimal(lon))
            self.assertEqual(poi.coordinates.latitude, Decimal(lat))
            m_pc.assert_called_once_with(category)


class PropertyCalMinSerializerTest(TestCase):
    def test_get_ical_events(self):
        instance = models.Property()
        request = mock.Mock(query_params={"from": "2020-01-01", "to": "2020-10-10"})

        serializer = serializers.PropertyCalMinSerializer(
            instance=instance, context={"request": request}
        )

        with self.assertRaises(ObjectDoesNotExist):
            instance.cozmo_calendar
        self.assertEqual(serializer.get_ical_events(instance), [])


class PropertyCreateSerializerTestCase(TestCase):

    serializer_class = serializers.PropertyCreateSerializer

    @classmethod
    def setUpTestData(cls):
        organization = Organization.objects.create()
        kwargs = {"user.organization": organization}
        cls.context = {"request": mock.MagicMock(**kwargs)}

    def test_create_with_all_data(self):
        data = {
            "name": "Some prop",
            "property_type": PropertyTypes.Camper_Rv.pretty_name,
            "rental_type": "Other",
            "location": {
                "continent": "",
                "country": "United States",
                "region": "CA",
                "state": "CA",
                "city": "San Francisco",
                "longitude": "-122.4220350",
                "latitude": "37.7634890",
            },
            "arrival_instruction": {
                "landlord": "Bob",
                "email": "bob@example.org",
                "phone": "+14153008000",
                "description": "The address is 594 Madrid Street, Apt. A, San Francisco, CA.",
            },
            "booking_settings": {
                "check_in_out": {"check_in_to": "16:00", "check_out_until": "11:00", "place": ""}
            },
            "pois": [
                {
                    "name": "Musuem",
                    "coordinates": {"longitude": "-122.4220350", "latitude": "37.7634890"},
                }
            ],
            "rates": [
                {"nightly": 399, "time_frame": {"lower": "2019-12-20", "upper": "2020-12-20"}}
            ],
            "fees": [{"name": "Test Fee", "value": 399}],
            "taxes": [{"name": "Test Tax", "value": 101}],
            "descriptions": {"notes": "Some notes", "headline": "Some headline"},
        }
        ser = self.serializer_class(data=data, context=self.context)
        self.assertTrue(ser.is_valid(), ser.errors)
        instance = ser.save()
        instance.refresh_from_db()
        # self.assertIsNotNone(instance.owner)
        self.assertIsNotNone(instance.location)
        self.assertIsNotNone(instance.arrival_instruction)
        self.assertIsNotNone(instance.booking_settings)
        self.assertIsNotNone(instance.descriptions)
        self.assertIsNotNone(instance.scheduling_assistant)
        self.assertEqual(instance.additionalfee_set.count(), len(data["fees"] + data["taxes"]))

        with self.subTest("booking_settings should have check_in_out filled in"):
            check_in_out = instance.booking_settings.check_in_out
            self.assertIsNotNone(check_in_out)
            for attr, value in data["booking_settings"]["check_in_out"].items():
                self.assertEqual(getattr(check_in_out, attr), value)

        self._create_from_serializer_output(instance)

    def test_create_with_little_data(self):
        data = {"name": "Some prop"}
        ser = self.serializer_class(data=data, context=self.context)
        self.assertTrue(ser.is_valid())
        instance = ser.save()
        self.assertFalse(instance.owner)
        self.assertFalse(instance.location)
        self.assertFalse(instance.arrival_instruction)
        self.assertTrue(hasattr(instance, "booking_settings"))
        self.assertEqual(instance.additionalfee_set.count(), 0)

        self._create_from_serializer_output(instance)

    def test_create_with_images_urls(self):
        images = [{"url": "http://example.org/1"}, {"url": "http://example.org/2"}]
        data = {
            "name": "Some prop",
            "property_type": "Other",
            "rental_type": "Other",
            "images": images,
        }
        ser = self.serializer_class(data=data, context=self.context)
        self.assertTrue(ser.is_valid(), ser.errors)
        instance = ser.save()
        self.assertEqual(len(instance.image_set.all()), len(images))

    def test_create_with_videos_urls(self):
        videos = [{"url": "http://example.org/1"}, {"url": "http://example.org/2"}]
        data = {
            "name": "Some prop",
            "property_type": "Other",
            "rental_type": "Other",
            "videos": videos,
        }
        ser = self.serializer_class(data=data, context=self.context)
        self.assertTrue(ser.is_valid(), ser.errors)
        instance = ser.save()
        self.assertEqual(len(instance.video_set.all()), len(videos))

    def _create_from_serializer_output(self, instance):
        # with self.subTest("Create from serializer output"):
        #     data = self.serializer_class(instance=instance).data
        #     del data["pois"]
        #     serializer = self.serializer_class(data=data, context=self.context)
        #     self.assertTrue(serializer.is_valid(), serializer.errors)
        pass


class PropertyListSerializerTestCase(TestCase):

    serializer_class = serializers.PropertyListSerializer

    def test_is_from_api(self):
        instance = models.Property(rental_connection_id=13)
        serializer = self.serializer_class(instance=instance)
        self.assertTrue(serializer.data["is_from_api"])


class DiscountSerializerTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ser = serializers.DiscountSerializer()
        cls.valid_data = {"is_percentage": True, "value": 50, "calculation_method": "Per Stay"}

    def test_validate(self):
        validated = self.ser.validate(self.valid_data)
        self.assertDictEqual(validated, self.valid_data)

    def test_invalid_percent(self):
        data = self.valid_data.copy()

        data["value"] = Decimal("100.001")
        with self.assertRaises(ValidationError):
            self.ser.validate(data)

        data["value"] = Decimal("0")
        with self.assertRaises(ValidationError):
            self.ser.validate(data)


# class PropertyCoverImageTestCase(TestCase):
#     def test_get_cover_image(self):
#         with self.subTest(msg="Our CDN-hosted image"):
#             prop = models.Property.objects.create(
#                 name="Name",
#                 property_type=models.Property.Types.Apartment.value,
#                 rental_type=models.Property.Rentals.Private.value,
#             )
#             db_img_url = "some/relative/path.png"
#             models.Image.objects.create(prop=prop, url=db_img_url)
#             self.assertTrue(prop.cover_image.startswith("https://"))
#             self.assertTrue(prop.cover_image.endswith(db_img_url))
#
#         with self.subTest(msg="Third-party hosted image"):
#             prop = models.Property.objects.create(
#                 name="Name",
#                 property_type=models.Property.Types.Apartment.value,
#                 rental_type=models.Property.Rentals.Private.value,
#             )
#             db_img_url = "https://some.cdn/absolute/path.png"
#             models.Image.objects.create(prop=prop, url=db_img_url)
#             self.assertTrue(prop.cover_image.startswith("https://"))
#             self.assertTrue(prop.cover_image.endswith(db_img_url))
#             self.assertEqual(prop.cover_image, db_img_url)


class RateSerializerTestMixin:
    serializer_class = None

    @classmethod
    def setUpTestData(cls):
        cls.prop = models.Property.objects.create(
            name="Name",
            property_type=models.Property.Types.Apartment.value,
            rental_type=models.Property.Rentals.Private.value,
        )

        cls.ser = cls.serializer_class()

    def tearDown(self):
        models.Rate.objects.all().delete()

    def test_do_not_accepts_inf_time_frame(self):
        data = {"time_frame": {"lower": None, "upper": None}, "nightly": 0, "prop": self.prop.id}
        serializer = self.serializer_class(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("time_frame", serializer.errors)

    def test_validate_time_frame(self):
        today = date.today()

        with self.subTest(msg="Equal dates"):
            data = DateRange(today, today)
            self.assertEqual(self.ser.validate_time_frame(data), data)

        with self.subTest(msg="End after start"):
            data = DateRange(today, today + timedelta(days=1))
            self.assertEqual(self.ser.validate_time_frame(data), data)

        with self.subTest(msg="End before start"), self.assertRaises(ValidationError):
            data = DateRange(today + timedelta(days=1), today)
            self.ser.validate_time_frame(data)

        with self.subTest(msg="No end"), self.assertRaises(ValidationError):
            data = DateRange(today, None)
            self.ser.validate_time_frame(data)

        with self.subTest(msg="No start"), self.assertRaises(ValidationError):
            data = DateRange(None, today)
            self.ser.validate_time_frame(data)

        with self.subTest(msg="Unboud time_frame"):
            ser = serializers.RateSerializer(
                data={"time_frame": {}, "prop": self.prop.pk, "nightly": "100.00"}
            )
            self.assertFalse(ser.is_valid())
            self.assertIn("time_frame", ser.errors)

        with self.subTest(msg="Empty time_frame"):
            ser = serializers.RateSerializer(
                data={"time_frame": {"empty": True}, "prop": self.prop.pk, "nightly": "100.00"}
            )
            self.assertFalse(ser.is_valid())
            self.assertIn("time_frame", ser.errors)


class RateSerializerTestCase(RateSerializerTestMixin, TestCase):
    serializer_class = serializers.RateSerializer

    def test_update(self):
        data = {
            "prop": self.prop.pk,
            "nightly": "10.00",
            "time_frame": {"lower": date.today(), "upper": date.today()},
        }
        validated_data = data.copy()

        rate = models.Rate.objects.create(
            time_frame=(date.today(), date.today()), nightly=Decimal("10"), prop_id=self.prop.pk
        )

        with mock.patch.object(self.ser, "_intersect") as m_intersect, (
            mock.patch("listings.serializers.ModelSerializer.update")
        ):
            self.ser.update(rate, validated_data)
            self.assertIn("time_frame", validated_data)
            m_intersect.assert_called_once_with(data, instance=rate)

    @mock.patch("listings.serializers.ModelSerializer.update")
    def test_update_partial_call_intersect(self, m_update):
        rate = models.Rate.objects.create(
            time_frame=(date.today(), date.today() + timedelta(days=15)),
            nightly=Decimal("10"),
            prop_id=self.prop.pk,
        )
        not_interserct_keys = ("prop", "nightly", "extra_person_fee")

        with mock.patch.object(self.ser, "_intersect") as m_intersect:
            self.ser.update(rate, dict.fromkeys(not_interserct_keys))
            m_intersect.assert_not_called()

        with mock.patch.object(self.ser, "_intersect") as m_intersect:
            keys = not_interserct_keys + ("time_frame",)
            self.ser.update(rate, dict.fromkeys(keys))
            m_intersect.assert_called_once()

    def test_create(self):
        data = {
            "prop": self.prop.pk,
            "nightly": "10.00",
            "time_frame": DateRange("2020-10-20", "2020-10-30"),
        }
        validated_data = data.copy()

        with mock.patch.object(self.ser, "_intersect") as m_intersect, (
            mock.patch("listings.serializers.ModelSerializer.create")
        ):
            self.ser.create(validated_data)
            m_intersect.assert_called_once_with(data)

    def test_intersect_move_rate_after(self):
        day = timedelta(days=1)
        valid_from = date.today()
        valid_to = valid_from + 2 * day

        kwargs = {"nightly": Decimal("10"), "prop_id": self.prop.pk}
        rates = (
            models.Rate(time_frame=(valid_from - day, valid_from), **kwargs),  # remains
            models.Rate(time_frame=(valid_from, valid_to - day), **kwargs),  # to delete
            models.Rate(time_frame=(valid_to - day, valid_to + 3 * day), **kwargs),  # to move
        )
        models.Rate.objects.bulk_create(rates)

        self.ser._intersect({"prop": self.prop.pk, "time_frame": DateRange(valid_from, valid_to)})
        self.assertEqual(models.Rate.objects.count(), 2)
        self.assertTrue(
            models.Rate.objects.filter(time_frame__contained_by=(None, valid_from)).exists()
        )
        self.assertTrue(
            models.Rate.objects.filter(time_frame__contained_by=(valid_to, None)).exists()
        )
        self.assertFalse(
            models.Rate.objects.filter(time_frame__overlap=(valid_from, valid_to)).exists()
        )

    def test_intersect_move_rate_before(self):
        day = timedelta(days=1)
        valid_from = date.today()
        valid_to = valid_from + 2 * day

        kwargs = {"nightly": Decimal("10"), "prop_id": self.prop.pk}
        rates = (
            models.Rate(time_frame=(valid_from - day, valid_from + day), **kwargs),  # to move
            models.Rate(time_frame=(valid_from, valid_to - day), **kwargs),  # to delete
            models.Rate(time_frame=(valid_to, valid_to + 3 * day), **kwargs),  # remains
        )
        models.Rate.objects.bulk_create(rates)

        self.ser._intersect({"prop": self.prop.pk, "time_frame": DateRange(valid_from, valid_to)})
        self.assertEqual(models.Rate.objects.count(), 2)
        self.assertTrue(
            models.Rate.objects.filter(time_frame__contained_by=(None, valid_from)).exists()
        )
        self.assertTrue(
            models.Rate.objects.filter(time_frame__contained_by=(valid_to, None)).exists()
        )
        self.assertFalse(
            models.Rate.objects.filter(time_frame__overlap=(valid_from, valid_to)).exists()
        )

    def test_intersect_remain_rate_after(self):
        day = timedelta(days=1)
        valid_from = date.today()
        valid_to = valid_from + 2 * day

        models.Rate.objects.create(
            time_frame=(valid_to + day, valid_to + 2 * day),  # will remain
            nightly=Decimal("10"),
            prop=self.prop,
        )

        self.ser._intersect({"prop": self.prop.pk, "time_frame": DateRange(valid_from, valid_to)})
        self.assertEqual(models.Rate.objects.count(), 1)
        self.assertTrue(
            models.Rate.objects.filter(time_frame__contained_by=(valid_to + day, None)).exists()
        )

    def test_intersect_delete_intersecting_rates(self):
        day = timedelta(days=1)
        start = date.today()
        end = start + 4 * day

        kwargs = {"nightly": Decimal("10"), "prop_id": self.prop.pk}
        instance = models.Rate.objects.create(time_frame=(start, start + day), **kwargs)
        rates = (
            models.Rate(time_frame=(start - day, start), **kwargs),  # will remain
            models.Rate(time_frame=(start + day, start + 2 * day), **kwargs),  # will be deleted
            models.Rate(time_frame=(start + 2 * day, end), **kwargs),  # will be deleted
            models.Rate(time_frame=(end + day, None), **kwargs),  # will remain
        )
        models.Rate.objects.bulk_create(rates)

        self.ser._intersect(
            {"prop": self.prop.pk, "time_frame": DateRange(start, end)}, instance=instance
        )
        self.assertEqual(models.Rate.objects.count(), 3)
        self.assertTrue(
            models.Rate.objects.exclude(pk=instance.pk)
            .filter(time_frame__contained_by=(None, start))
            .exists()
        )
        self.assertTrue(
            models.Rate.objects.exclude(pk=instance.pk)
            .filter(time_frame__contained_by=(end, None))
            .exists()
        )

    def test_intersect_move_rate_contained(self):
        valid_from = date.today()
        valid_to = valid_from + timedelta(days=10)

        kwargs = {"nightly": Decimal("10"), "prop_id": self.prop.pk}
        rates = (models.Rate(time_frame=(valid_from, valid_to), **kwargs),)  # to move
        models.Rate.objects.bulk_create(rates)

        self.ser._intersect(
            {
                "prop": self.prop.pk,
                "time_frame": DateRange(
                    valid_from + timedelta(days=3), valid_to - timedelta(days=3)
                ),
            }
        )
        self.assertEqual(models.Rate.objects.count(), 2)
        self.assertTrue(
            models.Rate.objects.filter(
                time_frame=(valid_from, valid_from + timedelta(days=3))
            ).exists()
        )
        self.assertTrue(
            models.Rate.objects.filter(
                time_frame=(valid_to - timedelta(days=3), valid_to)
            ).exists()
        )


class ReservationSerializerTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.MAX_GUESTS = 2
        cls.org = Organization.objects.create()
        cls.prop = models.Property.objects.create(
            name="Name",
            max_guests=cls.MAX_GUESTS,
            property_type=models.Property.Types.Apartment.value,
            rental_type=models.Property.Rentals.Private.value,
            organization=cls.org,
        )

        models.PricingSettings.objects.create(nightly=Decimal("10.00"), prop=cls.prop)
        models.AvailabilitySettings.objects.create(min_stay=2, max_stay=5, prop=cls.prop)

        cls.guest = Contact.objects.create(
            first_name="test",
            last_name="test",
            organization=cls.org
        )
        cls.now = date.today()

    def setUp(self):
        self.valid_data = {
            "guests_adults": self.MAX_GUESTS,
            "guests_children": 0,
            "start_date": self.now,
            "end_date": self.now + timedelta(days=3),
            "paid": 0,
            "prop": self.prop.id,
        }

    def get_serializer(self, data, instance=None):
        self.valid_data.update(data)
        return serializers.ReservationSerializer(
            instance=instance,
            data=self.valid_data,
            context={"organization": self.prop.organization},
        )

    def test_validate_with_price(self):
        price = Decimal("1000.98")
        ser = self.get_serializer({"price": price})
        with mock.patch("listings.serializers.models.Reservation.calculate_price") as m_calc:
            ser.is_valid()
            m_calc.assert_not_called()

    def test_invalid_start_end(self):
        ser = self.get_serializer({"end_date": self.valid_data["start_date"] - timedelta(days=1)})
        with self.assertRaises(ValidationError):
            ser.is_valid(raise_exception=True)

    def test_invalid_max_guests(self):
        ser = self.get_serializer({"guests_adults": self.MAX_GUESTS, "guests_children": 2})
        self.assertTrue(
            ser.is_valid(), f"We should allow user to ignore max guests constraint: {ser.errors}"
        )

    def test_invalid_stay_length(self):
        with self.subTest("Too long stay"):
            max_stay = self.prop.availability_settings.max_stay
            ser = self.get_serializer(
                {"start_date": self.now, "end_date": self.now + timedelta(days=max_stay + 1)}
            )
            self.assertFalse(ser.is_valid())

        with self.subTest("Too short stay"):
            min_stay = self.prop.availability_settings.min_stay
            ser = self.get_serializer(
                {"start_date": self.now, "end_date": self.now + timedelta(days=min_stay - 1)}
            )
            self.assertFalse(ser.is_valid())

    @mock.patch("listings.serializers.models.Reservation.calculate_price")
    def test_price(self, m_calc):
        ser = self.get_serializer({})
        with self.subTest(msg="Based on instance"):
            ser._get_price({"prop": self.prop})
            m_calc.assert_called_once()

        m_calc.reset_mock()
        with self.subTest(msg="Based on id"):
            ser._get_price({"prop": self.prop.pk})
            m_calc.assert_called_once()

    def test_expiration(self):
        instance = models.Reservation.objects.create(
            start_date=self.now,
            end_date=self.now + timedelta(days=3),
            price=Decimal("0"),
            base_total=Decimal("0"),
            paid=Decimal("0.00"),
            prop=self.prop,
            status=models.Reservation.Statuses.Inquiry,
            guest=self.guest
        )
        with self.subTest("Reservation inquiry Not Expired"):
            instance.expiration = timezone.now() + timedelta(days=1)
            instance.save()

            ser = self.get_serializer(
                {"status": models.Reservation.Statuses.Accepted.pretty_name}, instance=instance
            )
            self.assertTrue(ser.is_valid(), ser.errors)

        with self.subTest("Reservation inquiry expired"):
            instance.expiration = timezone.now() - timedelta(days=1)
            instance.save()

            ser = self.get_serializer(
                {"status": models.Reservation.Statuses.Accepted.pretty_name}, instance=instance
            )
            with self.assertRaises(ValidationError):
                ser.is_valid(raise_exception=True)
                self.assertIn("expiration", ser.errors)

        with self.subTest("Update expiration on expired inquiry"):
            instance.expiration = timezone.now() - timedelta(days=3)
            instance.save()

            serializer = self.get_serializer(
                {"expiration": timezone.now() + timedelta(days=3)}, instance=instance
            )
            self.assertTrue(serializer.is_valid(), serializer.errors)

        with self.subTest("Updated expiration on expired accepted reservation"):
            instance.status = models.Reservation.Statuses.Accepted
            instance.expiration = timezone.now() - timedelta(days=3)
            instance.save()

            serializer = self.get_serializer(
                {"expiration": timezone.now() + timedelta(days=3)}, instance=instance
            )
            self.assertTrue(serializer.is_valid(), serializer.errors)

        with self.subTest("Expiration is None"):
            serializer = self.get_serializer({"expiration": None}, instance=instance)
            self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_change_reservation_duration(self):
        serializer = self.get_serializer({"status": ReservationStatuses.Inquiry.pretty_name})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        reservation = serializer.save()

        shorten = [
            {
                "start_date": reservation.start_date,
                "end_date": reservation.end_date - timedelta(days=1),
            },
            {
                "start_date": reservation.start_date + timedelta(days=1),
                "end_date": reservation.end_date,
            },
        ]
        extended = [
            {
                "start_date": reservation.start_date,
                "end_date": reservation.end_date + timedelta(days=1),
            },
            {
                "start_date": reservation.start_date - timedelta(days=1),
                "end_date": reservation.end_date,
            },
        ]

        with self.subTest("Can change non-accepted reservation"):
            for data in shorten:
                serializer = self.get_serializer(data, instance=reservation)
                self.assertTrue(serializer.is_valid())

            for data in extended:
                serializer = self.get_serializer(data, instance=reservation)
                self.assertTrue(serializer.is_valid())

        reservation.status = ReservationStatuses.Accepted
        reservation.save()
        self.valid_data.pop("status")

        with self.subTest("Can shorten accepted reservation"):
            for data in shorten:
                serializer = self.get_serializer(data, instance=reservation)
                self.assertTrue(serializer.is_valid())

        with self.subTest("Can extend accepted reservation"):
            for data in extended:
                serializer = self.get_serializer(data, instance=reservation)
                self.assertTrue(serializer.is_valid())

    def test_create(self):
        user = User.objects.create(username="user")
        user.organization = Organization.objects.create()
        kwargs = {"user": user}
        context = {"request": mock.MagicMock(**kwargs), "organization": user.organization}
        security_deposit_value = 20

        prop = models.Property.objects.create(
            name="Name",
            property_type=models.Property.Types.Apartment.value,
            rental_type=models.Property.Rentals.Private.value,
            organization=user.organization,
        )
        models.PricingSettings.objects.create(
            nightly=100, security_deposit=security_deposit_value, prop=prop
        )

        models.Rate.objects.create(
            nightly=Decimal("200"), time_frame=(date(2018, 2, 10), None), prop=prop
        )

        models.AdditionalFee.objects.create(
            value=10,
            optional=False,
            calculation_method=CalculationMethod.Per_Stay.value,
            prop=prop,
        )

        models.AdditionalFee.objects.create(
            value=1, optional=False, calculation_method=CalculationMethod.Daily.value, prop=prop
        )

        models.AdditionalFee.objects.create(
            value=1,
            optional=False,
            calculation_method=CalculationMethod.Per_Person_Per_Day.value,
            prop=prop,
        )

        models.AdditionalFee.objects.create(
            value=10,
            optional=False,
            calculation_method=CalculationMethod.Per_Person_Per_Stay.value,
            prop=prop,
        )

        models.AdditionalFee.objects.create(
            value=2,
            optional=False,
            calculation_method=CalculationMethod.Per_Stay_Percent.value,
            prop=prop,
        )

        models.AdditionalFee.objects.create(
            value=2,
            optional=False,
            calculation_method=CalculationMethod.Per_Stay_Only_Rates_Percent.value,
            prop=prop,
        )

        models.AdditionalFee.objects.create(
            value=2,
            optional=False,
            calculation_method=CalculationMethod.Per_Stay_No_Taxes_Percent.value,
            prop=prop,
        )

        models.Discount.objects.create(
            value=2,
            prop=prop,
            is_percentage=False,
            days_before=10,
            discount_type=models.Discount.Types.Late_Bird.value,
            calculation_method=CalculationMethod.Per_Stay.value,
        )

        models.Discount.objects.create(
            value=4,
            prop=prop,
            is_percentage=True,
            days_before=10,
            discount_type=models.Discount.Types.Late_Bird.value,
            calculation_method=CalculationMethod.Per_Stay.value,
        )

        self.guest = Contact.objects.create(
            first_name="test",
            last_name="test",
            organization=user.organization
        )
        data = {
            "start_date": "2018-02-08",
            "end_date": "2018-02-12",
            "guests_adults": 2,
            "guests_children": 0,
            "pets": 1,
            "rebook_allowed_if_cancelled": True,
            "external_id": "sdf45z",
            "connection_id": "sdf45x",
            "confirmation_code": "sdf45y",
            "prop": prop.id,
            "paid": 0,
        }

        ser = serializers.ReservationSerializer(data=data, context=context)
        self.assertTrue(ser.is_valid(), ser.errors)
        instance = ser.save()
        self.assertTrue(instance.prop)
        self.assertEqual(
            instance.reservationfee_set.count(),
            prop.additionalfee_set.count(),
            "Number of reservation fees should be number of prop fees + 1 for security deposit",
        )

        feeAmount = instance.reservationfee_set.aggregate(total=Sum("value"))
        self.assertEqual(feeAmount["total"], Decimal("59.68") + security_deposit_value)

        self.assertEqual(instance.base_total, Decimal("600.00"))

        self.assertEqual(instance.reservationdiscount_set.count(), 2)

        discountAmount = instance.reservationdiscount_set.aggregate(total=Sum("value"))
        self.assertEqual(discountAmount["total"], Decimal("26.00"))

    def test_create_with_custom_base_total(self):
        user = User.objects.create(username="user")
        user.organization = Organization.objects.create()
        kwargs = {"user": user}
        context = {"request": mock.MagicMock(**kwargs), "organization": user.organization}
        security_deposit_value = 20

        prop = models.Property.objects.create(
            name="Name",
            property_type=models.Property.Types.Apartment.value,
            rental_type=models.Property.Rentals.Private.value,
            organization=user.organization,
        )
        models.PricingSettings.objects.create(
            nightly=100, security_deposit=security_deposit_value, prop=prop
        )

        self.guest = Contact.objects.create(
            first_name="test",
            last_name="test",
            organization=user.organization
        )
        data = {
            "start_date": "2018-02-08",
            "end_date": "2018-02-12",
            "guests_adults": 2,
            "guests_children": 0,
            "pets": 1,
            "base_total": "100000.00",
            "rebook_allowed_if_cancelled": True,
            "external_id": "sdf45z",
            "connection_id": "sdf45x",
            "confirmation_code": "sdf45y",
            "prop": prop.id,
            "paid": 0,
        }

        ser = serializers.ReservationSerializer(data=data, context=context)
        self.assertTrue(ser.is_valid(), ser.errors)
        instance = ser.save()
        self.assertTrue(instance.prop)

        self.assertEqual(instance.base_total, Decimal("100000.00"))

        self.assertEqual(instance.price, Decimal("100000.00"))

    def test_update_fees_discounts(self):
        reservation = models.Reservation.objects.create(
            start_date=date.today(),
            end_date=date.today() + timedelta(days=3),
            paid=Decimal("0.00"),
            price=Decimal("0.00"),
            base_total=Decimal("0.00"),
            prop=self.prop,
            guest=self.guest
        )
        models.ReservationFee.objects.create(reservation=reservation, value=10)
        models.ReservationDiscount.objects.create(
            reservation=reservation, value=10, discount_type=models.Discount.Types.Early_Bird
        )

        serializer = serializers.ReservationSerializer(
            data={"fees": [], "discounts": []},
            instance=reservation,
            partial=True,
            context={"organization": self.prop.organization},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()

        self.assertEqual(reservation.reservationfee_set.all().count(), 0)
        self.assertEqual(reservation.reservationdiscount_set.all().count(), 0)


class RoomSerializerTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.prop = models.Property.objects.create(
            name="prop",
            property_type=models.Property.Types.Condo.value,
            rental_type=models.Property.Rentals.Private.value,
        )
        cls.room_data = {
            "description": "Room name",
            "type": "Bathroom",
            "features": [{"name": "Some amenity", "value": 2}],
        }
        cls.room = models.Room.objects.create(
            description="Room name", room_type=models.Room.Types.Bathroom.value, prop=cls.prop
        )

    @classmethod
    def tearDownClass(cls):
        models.Room.objects.all().delete()
        cls.prop.delete()
        super().tearDownClass()

    def test_create(self):
        ser = serializers.RoomSerializer(data=self.room_data)
        self.assertTrue(ser.is_valid(), ser.errors)
        room = ser.save(prop_id=self.prop.pk)
        self.assertEqual(len(self.room_data["features"]), room.features.count())

    def test_update(self):
        ser = serializers.RoomSerializer(self.room, data=self.room_data)
        self.assertTrue(ser.is_valid(), ser.errors)
        room = ser.save()
        self.assertEqual(self.room.pk, room.pk)
        self.assertEqual(len(self.room_data["features"]), room.features.count())

    def test_partial_update(self):
        ser = serializers.RoomSerializer(self.room, data=self.room_data, partial=True)
        self.assertTrue(ser.is_valid(), ser.errors)
        with self.assertRaises(ValidationError):
            ser.save()


# class PropertyUpdateSerializerTestCase(TestCase):
#     serializer_class = serializers.PropertyUpdateSerializer
#
#     def setUp(self):
#         self.prop = models.Property.objects.create(
#             name="prop",
#             property_type=models.Property.Types.Condo.value,
#             rental_type=models.Property.Rentals.Private.value,
#         )
#         self.user = User.objects.create(
#             username="test",
#             first_name="some first name",
#             last_name="some last name",
#             is_superuser=True,
#         )
#         self.organization = Organization.objects.create()
#         self.owner = Owner.objects.create(
#             user=self.user,
#             organization=self.organization
#         )
#
#     def tearDown(self):
#         self.prop.delete()
#
#     def test_update_with_all_data(self):
#         new_name = "Some new name"
#
#         self.assertNotEqual(self.prop.name, new_name)
#         self.assertFalse(hasattr(self.prop, "basic_amenities"))
#         self.assertIsNone(self.prop.arrival_instruction)
#         self.assertFalse(hasattr(self.prop, "booking_settings"))
#         self.assertIsNone(self.prop.owner)
#         data = {
#             "id": self.prop.pk,
#             "name": new_name,
#             "max_guests": 5,
#             "arrival_instruction": {
#                 "landlord": "Bob",
#                 "email": "bob@example.org",
#                 "phone": "+14153008000",
#                 "description": "The address is 594 Madrid Street, Apt. A, San Francisco, CA.",
#             },
#             "basic_amenities": {"laundry": True},
#             "booking_settings": {"months_advanced_bookable": 6},
#             "pricing_settings": {"nightly": 150},
#             "location": {
#                 "continent": "",
#                 "country": "United States",
#                 "region": "CA",
#                 "state": "CA",
#                 "city": "San Francisco",
#                 "longitude": "-122.4220350",
#                 "latitude": "37.7634890",
#             },
#             "owner": self.owner.pk,
#         }
#         ser = self.serializer_class(self.prop, data=data, partial=True)
#         self.assertTrue(ser.is_valid(), ser.errors)
#         prop = ser.save()
#         self.assertEqual(prop.name, new_name)
#         self.assertTrue(self.prop.basic_amenities.laundry)
#         self.assertIsNotNone(self.prop.arrival_instruction)
#         self.assertIsNotNone(self.prop.booking_settings)
#         self.assertIsNone(self.prop.booking_settings.check_in_out)
#         self.assertIsNotNone(self.prop.owner)
#
#         with self.subTest("Update check in/out information"):
#             self.assertIsNone(prop.booking_settings.check_in_out)
#
#             booking_settings_data = {
#                 "booking_settings": {
#                     "check_in_out": {
#                         "check_in_to": "19:00",
#                         "check_out_until": "12:00",
#                         "place": "",
#                     }
#                 }
#             }
#             ser = self.serializer_class(self.prop, data=booking_settings_data, partial=True)
#             self.assertTrue(ser.is_valid(), ser.errors)
#             prop = ser.save()
#
#             check_in_out = prop.booking_settings.check_in_out
#             self.assertIsNotNone(check_in_out)
#             for attr, value in booking_settings_data["booking_settings"]["check_in_out"].items():
#                 self.assertEqual(getattr(check_in_out, attr), value)
#
#         with self.subTest("Update pricing settings"):
#             pricing_settings_id = prop.pricing_settings.id
#             data = {"pricing_settings": {"nightly": 200}}
#             ser = self.serializer_class(self.prop, data=data, partial=True)
#             self.assertTrue(ser.is_valid(), ser.errors)
#             prop = ser.save()
#             prop.refresh_from_db()
#             self.assertEqual(prop.pricing_settings.id, pricing_settings_id)
#
#     def test_update_with_little_data(self):
#         new_name = "Some new name"
#
#         self.assertNotEqual(self.prop.name, new_name)
#         data = {"id": self.prop.pk, "name": new_name}
#         ser = self.serializer_class(self.prop, data=data, partial=True)
#         self.assertTrue(ser.is_valid())
#         prop = ser.save()
#         self.assertEqual(prop.name, new_name)
#
#     def test_update_not_substitute(self):
#         owner = Owner.objects.create(user=self.user, organization=self.organization)
#         self.prop.owner = owner
#         self.prop.save()
#
#         self.assertEqual(owner.user, self.user)
#         self.assertEqual(owner.organization, self.organization)
#
#         data = {"id": self.prop.pk, "owner": {"last_name": last_name}}
#         ser = self.serializer_class(self.prop, data=data, partial=True)
#         self.assertTrue(ser.is_valid())
#         prop = ser.save()
#         self.assertEqual(prop.owner_id, owner.pk)
#         self.assertEqual(prop.owner.user.last_name, last_name)
#
#     def test_update_with_nones(self):
#         data = {
#             "rates": [
#                 {"time_frame": {"lower": "2018-01-01", "upper": "2020-01-01"}, "nightly": 10}
#             ],
#             "availabilities": [{"time_frame": {"lower": "2018-01-01", "upper": "2020-01-01"}}],
#             "owner": None,
#             "location": None,
#             "booking_settings": None,
#         }
#         ser = self.serializer_class(self.prop, data=data, partial=True)
#         self.assertTrue(ser.is_valid(), ser.errors)
#         for key in data.keys():
#             self.assertIn(key, ser.data, f"Missing key: {key}")
#
#     def test_invalid_rental_property_types_pair(self):
#         data = {
#             "property_type": models.Property.Types.Campsite.pretty_name,
#             "rental_type": models.Property.Rentals.Shared.pretty_name,
#         }
#         serializer = self.serializer_class(self.prop, data=data, partial=True)
#         self.assertFalse(serializer.is_valid())
#         error_message = serializer.errors["non_field_errors"][0]
#         for key in data.keys():
#             self.assertIn(key, error_message)
#
#     def test_validate_pricing_settings(self):
#         instance = models.Property()
#         context = {"request": mock.Mock()}
#
#         with self.subTest("Create instance with no pricing settings"):
#             serializer = self.serializer_class(data={"pricing_settings": None}, context=context)
#             serializer.is_valid()
#             self.assertNotIn("pricing_settings", serializer.errors)
#
#         with self.subTest("Create instance with pricing settings"):
#             serializer = self.serializer_class(
#                 data={"pricing_settings": {"nightly": 100}}, context=context
#             )
#             serializer.is_valid()
#             self.assertNotIn("pricing_settings", serializer.errors)
#
#         with self.subTest("Update instance with no pricing settings"):
#             self.assertFalse(hasattr(instance, "pricing_settings"))
#             serializer = self.serializer_class(
#                 instance=instance, data={"pricing_settings": None}, partial=True
#             )
#             self.assertTrue(serializer.is_valid(), serializer.errors)
#
#         with self.subTest("Update instance with pricing settings"):
#             instance.pricing_settings = models.PricingSettings.objects.create(nightly=100)
#             self.assertIsNotNone(instance.pricing_settings)
#             serializer = self.serializer_class(
#                 instance=instance, data={"pricing_settings": None}, partial=True
#             )
#             self.assertTrue(serializer.is_valid(), serializer.errors)
#
#     def test_clear_features(self):
#         context = {"request": mock.Mock()}
#
#         serializer = self.serializer_class(
#             instance=self.prop,
#             data={"features": [{"name": "Garage"}]},
#             partial=True,
#             context=context,
#         )
#         self.assertTrue(serializer.is_valid(), serializer.errors)
#         serializer.save()
#         self.assertEqual(self.prop.features.count(), 1)
#
#         serializer = self.serializer_class(
#             instance=self.prop, data={"features": []}, partial=True, context=context
#         )
#         self.assertTrue(serializer.is_valid(), serializer.errors)
#         serializer.save()
#         self.assertEqual(self.prop.features.count(), 0)


class FeatureSerializerTestCase(TestCase):
    def test_to_representation(self):
        name = "Hot Tube"
        override = "Worm Tube"

        with self.subTest("Feature have override but is disable"):
            feature = models.Feature.objects.create(name=name, override=override, display=False)
            ser = serializers.FeatureSerializer(feature)
            self.assertEqual(ser.data.get("name"), name)

        with self.subTest("Feature have override and is enabled"):
            feature = models.Feature.objects.create(name=name, override=override, display=True)
            ser = serializers.FeatureSerializer(feature)
            self.assertEqual(ser.data.get("name"), override)

        with self.subTest("Feature does not have override and is enabled"):
            feature = models.Feature.objects.create(name=name, override="", display=True)
            ser = serializers.FeatureSerializer(feature)
            self.assertEqual(ser.data.get("name"), name)

        with self.subTest("Feature does not have override but is disable"):
            feature = models.Feature.objects.create(name=name, override="", display=False)
            ser = serializers.FeatureSerializer(feature)
            self.assertEqual(ser.data.get("name"), name)


class SeasonalRateSerializerTestCase(RateSerializerTestMixin, TestCase):
    serializer_class = serializers.SeasonalRateSerializer

    def test_custom_and_seasonal_rates_not_overrides_each_other(self):
        valid_from = date.today()
        valid_to = valid_from + timedelta(days=1)

        seasonal_rate = {
            "prop": self.prop,
            "nightly": 10,
            "seasonal": True,
            "time_frame": DateRange(valid_from, valid_to),
        }

        custom_rate = {
            "prop": self.prop,
            "nightly": 10,
            "time_frame": DateRange(valid_from, valid_to),
        }

        with self.subTest("Custom Rate will not override Seasonal Rate"):
            self.ser.create(seasonal_rate)
            serializers.RateSerializer().create(custom_rate)

            self.assertEqual(models.Rate.objects.count(), 2)
            models.Rate.objects.all().delete()

        with self.subTest("Seasonal Rate will not override Custom Rate"):
            serializers.RateSerializer().create(custom_rate)
            self.ser.create(seasonal_rate)

            self.assertEqual(models.Rate.objects.count(), 2)
            models.Rate.objects.all().delete()


class PropertyCalSerializerTest(TestCase):
    serializer_class = serializers.PropertyCalSerializer

    @classmethod
    def setUpTestData(cls):
        cls.instance = models.Property.objects.create(name="Name")
        cls.instance.reservation_included = []
        cls.instance.rate_included = []
        cls.instance.blocking_included = []

    def test_includes_max_guests(self):
        serializer = self.serializer_class(
            instance=self.instance,
            context={
                "request": mock.Mock(
                    **{"query_params.from": "2019-01-01", "query_params.to": "2019-02-20"}
                )
            },
        )
        self.assertIn("max_guests", serializer.data)

    def test_base_rate(self):
        instance = models.Property()

        with self.subTest("No pricing and availability data"):
            self.assertFalse(hasattr(instance, "pricing_settings"))
            self.assertFalse(hasattr(instance, "availability_settings"))

            serializer = self.serializer_class()
            base_rate = serializer.get_base_rate(instance)
            for key, value in base_rate.items():
                self.assertIsNone(value, f"'{key}' should be None")

        with self.subTest("Pricing and availability data exists"):
            instance.pricing_settings = models.PricingSettings(nightly=100, weekend=120)
            instance.availability_settings = models.AvailabilitySettings(min_stay=5)
            base_rate = serializer.get_base_rate(instance)
            self.assertNotIn(None, base_rate.values())


class TaxSerializerTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        models.Property.objects.all().delete()
        cls.prop = models.Property.objects.create(
            name="Name",
            property_type=models.Property.Types.Apartment.value,
            rental_type=models.Property.Rentals.Private.value,
        )

    def test_serializer_accept_only_tax_type_fees(self):
        tax_serializer = serializers.TaxSerializer(
            data={
                "name": "test",
                "value": "80",
                "type": "Booking Fee",
                "optional": False,
                "taxable": False,
                "refundable": False,
                "order": 1,
                "calculation_method": "Daily",
                "prop": self.prop.id,
            }
        )
        self.assertEqual(tax_serializer.is_valid(), False)
        tax_serializer = serializers.TaxSerializer(
            data={
                "name": "test",
                "value": "80",
                "type": "Linen Fee",
                "optional": False,
                "taxable": False,
                "refundable": False,
                "order": 1,
                "calculation_method": "Daily",
                "prop": self.prop.id,
            }
        )
        self.assertEqual(tax_serializer.is_valid(), False)
        tax_serializer = serializers.TaxSerializer(
            data={
                "name": "test",
                "value": "80",
                "type": "Local Tax",
                "optional": False,
                "taxable": False,
                "refundable": False,
                "order": 1,
                "calculation_method": "Daily",
                "prop": self.prop.id,
            }
        )
        self.assertEqual(tax_serializer.is_valid(), True)


class FeeSerializerTest(TestCase):
    def get_serializer(self, data):
        return serializers.FeeSerializer(data=data, prop_required=True)

    @classmethod
    def setUpTestData(cls):
        models.Property.objects.all().delete()
        cls.prop = models.Property.objects.create(
            name="Name",
            property_type=models.Property.Types.Apartment.value,
            rental_type=models.Property.Rentals.Private.value,
        )

    def test_serializer_accept_only_fee_type_fees(self):
        fee_serializer = self.get_serializer(
            data={
                "name": "test",
                "value": "80",
                "type": "Resort Fee",
                "optional": False,
                "taxable": False,
                "refundable": False,
                "order": 1,
                "calculation_method": "Daily",
                "prop": self.prop.id,
            }
        )
        self.assertTrue(fee_serializer.is_valid(), fee_serializer.errors)
        fee_serializer = self.get_serializer(
            data={
                "name": "test",
                "value": "80",
                "type": "Local Tax",
                "optional": False,
                "taxable": False,
                "refundable": False,
                "order": 1,
                "calculation_method": "Daily",
                "prop": self.prop.id,
            }
        )
        self.assertFalse(fee_serializer.is_valid())
        fee_serializer = self.get_serializer(
            data={
                "name": "test",
                "value": "80",
                "type": "Local Tax",
                "optional": False,
                "taxable": False,
                "refundable": False,
                "order": 1,
                "calculation_method": "Daily",
                "prop": self.prop.id,
            }
        )
        self.assertFalse(fee_serializer.is_valid())

    def test_prop_required(self):
        serializer = self.get_serializer(
            data={
                "name": "test",
                "value": "80",
                "type": "Resort Fee",
                "optional": False,
                "taxable": False,
                "refundable": False,
                "order": 1,
                "calculation_method": "Daily",
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("prop", serializer.errors)
        self.assertIn(serializer.error_messages["required"], serializer.errors["prop"])

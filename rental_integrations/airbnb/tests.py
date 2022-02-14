"""
import json
import os.path
from datetime import date, timedelta
from itertools import chain
from unittest.mock import patch

from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase
from django.utils import timezone
from rest_framework.fields import HiddenField
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED, HTTP_400_BAD_REQUEST

from accounts.models import Organization
from app_marketplace.models import AirbnbApp
from listings import models as listings_models
from listings.serializers import PropertyCreateSerializer, ReservationSerializer
from . import models, service as air_service
from .choices import Amenity, PropertyType
from .mappings import cozmo_property_type, type_to_group
from .serializers import AirbnbAppDetailedSerializer, LinkSerializer
from .signals import push_to_airbnb
from .tasks import airbnb_push, airbnb_push_initial

# Service tests
LISTING_ID = 12_345_678
fixtures_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures/json_responses")
PRICING_SETTINGS_RESPONSE = {
    "pricing_setting": {
        "listing_currency": "USD",
        "default_daily_price": 55,
        "weekend_price": 100,
        "cleaning_fee": 100,
        "price_per_extra_person": 15,
        "security_deposit": 500,
        "guests_included": 2,
        "standard_fees": [
            {"fee_type": "PASS_THROUGH_RESORT_FEE", "amount": 5, "amount_type": "percent"}
        ],
        "monthly_price_factor": None,
        "weekly_price_factor": None,
    }
}

PRICING_SETTINGS_INPUT = PRICING_SETTINGS_RESPONSE["pricing_setting"]

KEY_LISTING_CURRENCY = "listing_currency"


class AirbnbServiceTestCase(TestCase):
    valid_response = HTTP_201_CREATED, json.dumps({"listing": {"id": 123}})
    invalid_response = HTTP_400_BAD_REQUEST, {"error": "some error occured"}

    @classmethod
    def setUpTestData(cls):
        cls.service = air_service.AirbnbService("user", "key")

    @patch.object(air_service.AirbnbService, "_call_api", return_value=valid_response)
    def test_push_new_listing(self, mock_call_api):
        for non_id in (None, ""):
            mock_call_api.reset_mock()
            self.service.push_listing({"id": None})
            self.assertEqual(mock_call_api.call_count, 1)
            _, data, http_method = mock_call_api.call_args_list[0][0]
            self.assertEqual(http_method.lower(), "post")

        with self.subTest("Invalid response"):
            mock_call_api.reset_mock()
            mock_call_api.return_value = self.invalid_response
            invalid_listing = self.service.push_listing({"id": None})
            mock_call_api.assert_called_once()
            self.assertIn("error", invalid_listing)

    @patch.object(air_service.AirbnbService, "_call_api", return_value=valid_response)
    def test_push_update_listing(self, mock_call_api):
        listing = {"id": 123}
        self.service.update_listing(listing)
        self.assertEqual(mock_call_api.call_count, 1)
        url, _, http_method = mock_call_api.call_args_list[0][0]
        self.assertEqual(http_method.lower(), "put")
        self.assertTrue(url.endswith(str(listing["id"])))

        url_last, data, http_method = mock_call_api.call_args_list[0][0]
        self.assertEqual(url, url_last)
        self.assertEqual(http_method.lower(), "put")

    @patch.object(air_service.AirbnbService, "_call_api")
    def test_push_photos(self, m_call_api):
        listing_id = "123"
        valid_response = {"listing_photo": {"listing_id": listing_id}}
        valid_responses = [(201, json.dumps(valid_response))] * 3
        invalid_responses = [(400, json.dumps(self.invalid_response))]
        responses = valid_responses + invalid_responses

        def push_photos(url, data, **kwargs):
            return responses.pop(0)

        m_call_api.side_effect = push_photos
        photos = [
            {"image": "base64-encoded-image", "caption": "Image #{i}"}
            for i, _ in enumerate(responses)
        ]

        airbnb_photos = self.service.push_photos(listing_id, photos)

        self.assertEqual(m_call_api.call_count, len(photos))
        self.assertEqual(airbnb_photos.count({}), len(invalid_responses))
        for photo in photos:
            self.assertIn("listing_id", photo)

    @patch.object(air_service.AirbnbService, "_call_api")
    def test_push_description(self, m_call_api):
        listing_id = "123"
        valid_response = (
            201,
            json.dumps({"listing_description": {"description": "Some description"}}),
        )
        description = {"en": {"area": "very fine"}}

        m_call_api.return_value = valid_response
        resp = self.service.push_descriptions(listing_id, description)
        m_call_api.assert_called_once()
        self.assertEqual(len(resp), len(description.keys()))

    @patch.object(air_service.AirbnbService, "_call_api")
    def test_get_listing(self, m_call_api):
        listing_id = "123"
        m_call_api.return_value = (200, json.dumps({"listing": {"name": "Some name"}}))
        resp = self.service.get_listing(listing_id)
        m_call_api.assert_called_once()
        self.assertIsInstance(resp, dict)

    @patch.object(air_service.AirbnbService, "_call_api")
    def test_get_listings(self, m_call_api):
        mock_data = {"id": 321, "name": "Some name"}
        limit = 50
        all_listings = int(limit * 1.5)
        m_call_api.side_effect = chain(
            [
                (200, json.dumps({"listings": [mock_data] * limit})),
                (200, json.dumps({"listings": [mock_data] * (all_listings - limit)})),
            ],
            [(200, json.dumps({"listing_photos": [mock_data]}))] * all_listings,
        )
        listings = self.service.get_listings()
        self.assertEqual(len(listings), all_listings)
        for listing in listings:
            self.assertIn("photos", listing)

    def test_to_airbnb(self):
        with self.subTest("Minimal property"):
            serializer = PropertyCreateSerializer(
                data={}, context={"organization": Organization.objects.create()}
            )
            self.assertTrue(serializer.is_valid(), serializer.errors)
            prop = serializer.save()
            airbnb_listing = self.service.to_airbnb(prop)
            self.assertIsInstance(json.dumps(airbnb_listing), str)

        with self.subTest("Amenities"):
            serializer = PropertyCreateSerializer(
                data={"basic_amenities": {"tv": True}},
                context={"organization": Organization.objects.create()},
            )
            self.assertTrue(serializer.is_valid(), serializer.errors)
            prop = serializer.save()
            airbnb_listing = self.service.to_airbnb(prop)
            self.assertIn("tv", airbnb_listing["amenity_categories"])

    def test_to_airbnb_availability(self):
        today = timezone.now().date()
        prop = listings_models.Property.objects.create()
        self.assertEqual(self.service.to_airbnb_availability(prop), [])

        listings_models.Reservation.objects.create(
            prop=prop, start_date=today, end_date=today + timedelta(days=1), price=100, paid=0
        )
        self.assertEqual(len(self.service.to_airbnb_availability(prop)), 1)

        listings_models.Blocking.objects.create(
            prop=prop, time_frame=(today, today + timedelta(days=1))
        )
        self.assertEqual(len(self.service.to_airbnb_availability(prop)), 2)

    def test_to_cozmo(self):
        airbnb_data = {
            "amenity_categories": [Amenity.hair_dryer.value, Amenity.wireless_internet.value],
            "apt": None,
            "bathrooms": 2.0,
            "bedrooms": 3,
            "beds": 3,
            "city": "St Helena",
            "country_code": "US",
            "directions": "Take a cab from the airport",
            "id": 21_425_420,
            "lat": 38.490_467,
            "lng": -122.460_449,
            "listing_price": 100,
            "listing_currency": "USD",
            "name": "Amazing House in Wine Country",
            "permit_or_tax_id": None,
            "person_capacity": 8,
            "property_type_category": "house",
            "requested_approval_status_category": "new",
            "room_type_category": "entire_home",
            "state": "CA",
            "street": "1691 Sulphur Springs Ave",
            "user_defined_location": True,
            "property_type_group": "apartments",
            "zipcode": "94574",
            "descriptions": {
                "name": "SOMA, 5 Min Walk to Moscone Center.",
                "locale": "en",
                "summary": "New summary.",
                "space": "New space.",
                "access": "New access.",
                "interaction": "New interaction.",
                "neighborhood_overview": "New neigborhood_overview.",
                "transit": "New transit.",
                "notes": "New notes.",
                "house_rules": "New house_rules.",
            },
            "booking_settings": {  # Warning: this is simplified response
                "cancellation_policy_category": "strict",
                "instant_booking_allowed_category": "off",
                "check_in_time_end": "FLEXIBLE",
                "check_in_time_start": "10",
                "check_out_time": 10,
                "instant_book_welcome_message": "Hello, good bye!",
                "listing_expectations_for_guests": [
                    {"type": "requires_stairs", "added_details": "be careful!"},
                    {"type": "weapons", "added_details": "no guns!"},
                ],
                "listing_id": LISTING_ID,
                "guest_controls": {
                    "allows_children_as_host": False,
                    "allows_infants_as_host": False,
                    "children_not_allowed_details": False,
                    "allows_smoking_as_host": False,
                    "allows_pets_as_host": False,
                    "allows_events_as_host": False,
                },
            },
            "pricing_settings": {
                "listing_currency": "USD",
                "default_daily_price": 55,
                "weekend_price": 100,
                "cleaning_fee": 100,
                "price_per_extra_person": 15,
                "security_deposit": 500,
                "guests_included": 2,
                "standard_fees": [
                    {"fee_type": "PASS_THROUGH_RESORT_FEE", "amount": 5, "amount_type": "percent"}
                ],
                "monthly_price_factor": None,
                "weekly_price_factor": None,
            },
            "photos": [
                {
                    "id": 63615,
                    "listing_id": LISTING_ID,
                    "caption": "Amazing photo",
                    "sort_order": 1,
                    "extra_large_url": "https://extra.large",
                    "large_url": "https://extra.large",
                    "small_url": "https://extra.large",
                    "thumbnail_url": "https://extra.large",
                }
            ],
            "listing_rooms": [
                {
                    "beds": [{"quantity": 3, "type": "couch"}],
                    "id": 145_443_453,
                    "listing_id": LISTING_ID,
                    "room_amenities": list(),
                    "room_number": 1,
                }
            ],
            "availability_rules": {
                "listing_id": LISTING_ID,
                "default_min_nights": 2,
                "default_max_nights": 10,
                "turnover_days": {"days": 5},
                "day_of_week_check_in": [{"day_of_week": 0}],
                "day_of_week_check_out": [{"day_of_week": 2}],
                "min_days_notice": {"days": 1},
                "max_days_notice": {"days": 90},
                "seasonal_min_nights": None,
                "booking_lead_time": {"hours": 1, "allow_request_to_book": 0},
                "day_of_week_min_nights": list(),
            },
        }
        data = self.service.to_cozmo(airbnb_data)
        serializer = PropertyCreateSerializer(
            data=data, context={"organization": Organization.objects.create()}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        instance = serializer.save()
        self.assertIsNotNone(instance.basic_amenities)
        self.assertIsNotNone(instance.booking_settings)
        self.assertIsNotNone(instance.booking_settings.check_in_out)
        self.assertIsNotNone(instance.descriptions)
        self.assertIsNotNone(instance.location)
        self.assertIsNotNone(instance.pricing_settings)
        self.assertIsNotNone(instance.availability_settings)

    @patch.object(air_service.AirbnbService, "_call_api")
    def test_push_pricing_settings_currency(self, m_call_api):
        mock_data = {KEY_LISTING_CURRENCY: PRICING_SETTINGS_INPUT[KEY_LISTING_CURRENCY]}
        m_call_api.return_value = HTTP_200_OK, json.dumps(PRICING_SETTINGS_RESPONSE)
        pricing_settings = self.service.push_listing_currency(LISTING_ID, mock_data)
        expected_value = {KEY_LISTING_CURRENCY: pricing_settings[KEY_LISTING_CURRENCY]}
        self.assertIsInstance(pricing_settings, dict)
        self.assertDictEqual(expected_value, mock_data)
        self.assertDictEqual(PRICING_SETTINGS_RESPONSE["pricing_setting"], pricing_settings)
        _, data, http_method = m_call_api.call_args_list[0][0]
        self.assertEqual(http_method.lower(), "put")

    @patch.object(air_service.AirbnbService, "_call_api")
    def test_push_pricing_settings_pricing(self, m_call_api):
        mock_data = PRICING_SETTINGS_INPUT.copy()
        mock_data.pop(KEY_LISTING_CURRENCY)
        m_call_api.return_value = HTTP_200_OK, json.dumps(PRICING_SETTINGS_RESPONSE)
        pricing_settings = self.service.push_pricing(LISTING_ID, mock_data)
        self.assertIsInstance(pricing_settings, dict)
        self.assertDictEqual(PRICING_SETTINGS_RESPONSE["pricing_setting"], pricing_settings)
        pricing_settings.pop(KEY_LISTING_CURRENCY)
        self.assertDictEqual(pricing_settings, mock_data)
        _, data, http_method = m_call_api.call_args_list[0][0]
        self.assertEqual(http_method.lower(), "put")

    @patch.object(air_service.AirbnbService, "_call_api")
    def test_push_pricing_settings(self, m_call_api):
        mock_data = PRICING_SETTINGS_INPUT.copy()
        mock_data[KEY_LISTING_CURRENCY] = "JPY"
        expected_response = mock_data.copy()
        currency_mock_data = {KEY_LISTING_CURRENCY: mock_data.get(KEY_LISTING_CURRENCY)}
        pricing_mock_data = {k: v for k, v in mock_data.items() if k not in currency_mock_data}

        m_call_api.side_effect = chain(
            [(HTTP_200_OK, json.dumps(PRICING_SETTINGS_RESPONSE))],
            [(HTTP_200_OK, json.dumps({"pricing_setting": mock_data}))],
        )
        pricing_settings = self.service.push_pricing_settings(LISTING_ID, mock_data)

        self.assertEqual(m_call_api.call_count, 2)
        self.assertDictEqual(pricing_settings, expected_response)
        _, data, _ = m_call_api.call_args_list[0][0]
        self.assertDictEqual(data, pricing_mock_data)
        _, data, _ = m_call_api.call_args_list[1][0]
        self.assertDictEqual(data, currency_mock_data)

    # def test_parse_data(self):
    #     data = {
    #         "name": "Some name",
    #         "price": 123,
    #         "cancellation_policy": None,
    #         "available": True,
    #         "amenities": ["kitchen", "ac", "wifi"],
    #         "owner": {"name": "Jack"},
    #     }
    #
    #     parsed = json.loads(self.service._parse_data(data))
    #     self.assertNotIn(None, parsed.values())

    @patch.object(air_service.AirbnbService, "_call_api")
    def test_push_availability(self, m_call_api):
        m_call_api.return_value = HTTP_201_CREATED, {"calendar_operation": {"days": []}}
        today = date.today()

        p = listings_models.Property.objects.create()
        listings_models.Blocking.objects.bulk_create(
            listings_models.Blocking(
                time_frame=(today + timedelta(days=i), today + timedelta(days=i + 1)), prop=p
            )
            for i in range(5)
        )
        listings_models.Reservation.objects.create(
            start_date=today, end_date=today + timedelta(days=5), price=1, paid=0, prop=p
        )
        self.assertIsInstance(self.service.push_availability("external_id", p), dict)

    def test_to_cozmo_reservation(self):
        organization = Organization.objects.create()
        prop = listings_models.Property.objects.create(organization=organization).id

        with open(f"{fixtures_dir}/get_reservations_response.json") as raw_json:
            data = json.load(raw_json)["reservations"][0]

        cozmo_reservation = self.service.to_cozmo_reservation(data)
        cozmo_reservation["prop"] = prop

        serializer = ReservationSerializer(
            data=cozmo_reservation, context={"organization": organization}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        reservation = serializer.save()
        self.assertGreater(reservation.reservationfee_set.count(), 0)
        self.assertIsNotNone(reservation.reservationrate)

    def test_get_throttles(self):
        url = "http://example.org/non-existing-fragment"
        self.assertIsInstance(self.service._get_throttles(url), set)

        url = "http://example.org" + list(self.service.throttles["endpoints"].keys())[0]
        self.assertIsInstance(self.service._get_throttles(url), set)


# Serializers tests


class AirbnbAppDetailSerializerTest(TestCase):
    def get_user(self):
        app = AirbnbApp.objects.create(organization=Organization.objects.create(), user_id=123)

        with self.assertRaises(ObjectDoesNotExist):
            app.airbnb_user

        serializer = AirbnbAppDetailedSerializer()
        self.assertEqual(serializer.get_user(app), {})


class LinkSerializerTest(TestCase):
    def get_serializer(self, instance=None, data=None):
        return LinkSerializer(instance=instance, data=data, context={"organization": self.org})

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create()
        cls.prop = listings_models.Property.objects.create(
            organization=cls.org,
            booking_settings=listings_models.BookingSettings.objects.create(
                check_in_out=listings_models.CheckInOut.objects.create()
            ),
        )
        listings_models.BasicAmenities.objects.create(prop=cls.prop)
        cls.app = AirbnbApp.objects.create(organization=cls.org, user_id=10)

    def tearDown(self):
        self.prop.airbnb_sync = None
        try:
            self.prop.airbnb_listing.delete()
        except models.ListingLegacy.DoesNotExist:
            pass
        self.prop.save()

    @property
    def valid_data(self):
        return {"id": self.prop.id, "airbnb_app": self.app.id, "airbnb_id": "some-id"}

    def test_invalid_data(self):
        airbnb_id = "some-id"
        other_org = Organization.objects.create()

        with self.subTest("Property from different organization"):
            other_prop = listings_models.Property.objects.create(organization=other_org)
            self.assertNotEqual(other_prop.organization, self.prop.organization)
            serializer = self.get_serializer(
                data={
                    "id": other_prop.id,
                    "airbnb_app": self.app.id,
                    "airbnb_id": airbnb_id,
                    "action": "export",
                }
            )
            self.assertFalse(serializer.is_valid())
            self.assertIn("id", serializer.errors)

        with self.subTest("Airbnb App from different organization"):
            other_app = AirbnbApp.objects.create(organization=other_org, user_id=123)
            self.assertNotEqual(other_prop.organization, self.prop.organization)
            serializer = self.get_serializer(
                data={
                    "id": self.prop.id,
                    "airbnb_app": other_app.id,
                    "airbnb_id": airbnb_id,
                    "action": "export",
                }
            )
            self.assertFalse(serializer.is_valid())
            self.assertIn("airbnb_app", serializer.errors)

        with self.subTest("All fields are required (beside 'action')"):
            serializer = self.get_serializer(data={})
            self.assertFalse(serializer.is_valid())
            visible_fields = (
                name
                for name, field in serializer.fields.items()
                if not isinstance(field, HiddenField) and name != "action"
            )

            for field_name in visible_fields:
                self.assertIn(serializer.error_messages["required"], serializer.errors[field_name])

    @patch(
        "rental_integrations.airbnb.serializers.AirbnbService.push_listing",
        return_value={"id": "some-id"},
    )
    def test_valid_data(self, m_push):
        with self.subTest("Create new Listing"):
            data = self.valid_data.copy()
            data["action"] = "export"

            serializer = self.get_serializer(data=data)
            with self.assertRaises(models.ListingLegacy.DoesNotExist):
                self.prop.airbnb_listing

            self.assertTrue(serializer.is_valid(), serializer.errors)
            serializer.save()
            self.prop.refresh_from_db()

            listing = self.prop.airbnb_listing
            self.assertIsInstance(listing, models.ListingLegacy)
            self.assertIsNotNone(self.prop.airbnb_sync)
            self.assertEqual(listing.external_id, self.valid_data["airbnb_id"])
            self.assertEqual(self.prop.airbnb_sync, listing.airbnb_app)

        with self.subTest("Update existing Listing"):
            data = self.valid_data.copy()
            data["airbnb_id"] += "different id"
            data["action"] = "export"

            serializer = self.get_serializer(data=data)
            self.assertTrue(serializer.is_valid(), serializer.errors)
            serializer.save()
            self.prop.refresh_from_db()

            listing = self.prop.airbnb_listing
            self.assertIsInstance(listing, models.ListingLegacy)
            self.assertEqual(listing.external_id, data["airbnb_id"])
            self.assertEqual(self.prop.airbnb_sync, listing.airbnb_app)

        with self.subTest("Unlink Listing"):
            data = self.valid_data.copy()
            data["airbnb_id"] = None
            data["action"] = "unlink"

            self.assertIsInstance(self.prop.airbnb_listing, models.ListingLegacy)
            self.assertIsInstance(self.prop.airbnb_sync, AirbnbApp)
            serializer = self.get_serializer(data=data)
            self.assertTrue(serializer.is_valid(), serializer.errors)
            serializer.save()
            self.prop.refresh_from_db()

            self.assertIsNone(self.prop.airbnb_sync)
            with self.assertRaises(models.ListingLegacy.DoesNotExist):
                self.prop.airbnb_listing

        with self.subTest("Fetch listing from Airbnb"):
            data = self.valid_data.copy()
            data["id"] = None
            data["action"] = "import"

            serializer = self.get_serializer(data=data)
            self.assertTrue(serializer.is_valid(), serializer.errors)

            new_name = "New prop name"
            with patch(
                "rental_integrations.airbnb.serializers.AirbnbService",
                spec=air_service.AirbnbService,
                **{
                    "get_detailed_listing.return_value": {"id": "external-id"},
                    "to_cozmo.return_value": {
                        "name": new_name,
                        "property_type": listings_models.Property.Types.Apartment.pretty_name,
                        "rental_type": listings_models.Property.Rentals.Private.pretty_name,
                        "status": listings_models.Property.Statuses.Active.pretty_name,
                    },
                },
            ):
                return_data = serializer.save()
            new_prop = listings_models.Property.objects.get(pk=return_data["id"])
            self.assertEqual(new_prop.name, new_name)
            self.assertEqual(new_prop.airbnb_sync_id, data["airbnb_app"])
            self.assertEqual(new_prop.airbnb_listing.external_id, data["airbnb_id"])

    def test_valid_data_no_action(self):
        with self.subTest("'action' is missing"):
            data = self.valid_data.copy()
            self.assertNotIn("action", data)
            serializer = self.get_serializer(data=data)
            self.assertTrue(serializer.is_valid(), serializer.errors)

        with self.subTest("'action' is None"):
            data = self.valid_data.copy()
            data["action"] = None
            serializer = self.get_serializer(data=data)
            self.assertTrue(serializer.is_valid(), serializer.errors)
            self.assertIsNotNone(serializer.data["action"])


# Signals tests


class PushAirbnbTest(TestCase):
    @patch("rental_integrations.airbnb.signals.AirbnbService.update_listing")
    def test_push(self, m_push_listing):
        app = AirbnbApp.objects.create(
            organization=Organization.objects.create(),
            user_id=123,
            access_token="access",
            refresh_token="refresh",
        )
        prop = listings_models.Property.objects.create(airbnb_sync=app)
        listings_models.BasicAmenities.objects.create(prop=prop)

        push_to_airbnb(listings_models.Property, prop)
        m_push_listing.assert_called_once()


# Tasks tests


class AirbnbPushTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.app = AirbnbApp.objects.create(
            organization=Organization.objects.create(),
            user_id=123,
            access_token="access",
            refresh_token="refresh",
        )
        cls.prop = listings_models.Property.objects.create()
        models.ListingLegacy.objects.create(external_id="", prop=cls.prop)
        cls.app.property_set.add(cls.prop)

    def test_push_initial(self):
        image_count = 10
        images = listings_models.Image.objects.bulk_create(
            listings_models.Image(prop=self.prop) for _ in range(image_count)
        )

        for image in images:
            with self.assertRaises(ObjectDoesNotExist):
                self.assertIsNone(image.airbnb_photo)

        external_id = "airbnb_id"
        listings = [
            {
                "id": external_id,
                "property_external_id": self.prop.id,
                "photos": [{"photo_id": i} for i in range(image_count)],
            }
        ]
        with patch(
            "rental_integrations.airbnb.tasks.AirbnbService.push_listings", return_value=listings
        ):
            airbnb_push_initial.s(self.app.id).apply()

        self.prop.refresh_from_db()
        self.assertEqual(self.prop.airbnb_listing.external_id, external_id)
        for image in self.prop.image_set.all():
            self.assertIsInstance(image.airbnb_photo, models.Photo)

    def test_push(self):
        apps_count = AirbnbApp.objects.all().count()

        with patch("rental_integrations.airbnb.tasks.AirbnbService.push_listings") as m_push:
            airbnb_push()
            self.assertEqual(m_push.call_count, apps_count)


# mappings tests


class MappingsTestCase(TestCase):
    def test_cozmo_property_type(self):
        with self.subTest("String property types are mapping to airbnb"):
            for prop_type in listings_models.Property.Types:
                mapped = cozmo_property_type[prop_type.value]
                if mapped is not None:
                    self.assertIsInstance(mapped, str, prop_type.pretty_name)

        with self.subTest("Enum property types are mapping to airbnb"):
            for prop_type in listings_models.Property.Types:
                mapped = cozmo_property_type[prop_type]
                if mapped is not None:
                    self.assertIsInstance(mapped, str, prop_type.pretty_name)

        with self.subTest("Invalid cozmo property type"):
            invalid_type = "xxx"
            with self.assertRaises(ValueError):
                listings_models.Property.Types(invalid_type)
            mapped = cozmo_property_type[invalid_type]
            self.assertIsNone(mapped)

    def test_type_to_group(self):
        for prop_type in PropertyType:
            group = type_to_group[prop_type.value]
            self.assertIsNotNone(group)
"""

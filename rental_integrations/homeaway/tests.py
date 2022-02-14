"""
from unittest.mock import MagicMock, patch

# For demo purposes
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.response import Response
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_202_ACCEPTED,
    HTTP_400_BAD_REQUEST,
)

from accounts.models import Organization
from listings.serializers import PropertyCreateSerializer
from rental_integrations.exceptions import ServiceException
from rental_integrations.models import IntegrationSetting
from rental_integrations.service import HTTP_499_NOT_MY_FAULT
from . import service as home_service
from .models import HomeAwayAccount, Listing
from .serializers import HomeAwayAccountSerializer
from .views import HomeAwayAccountViewSet

User = get_user_model()


# Serializers tests


class HomeAwayAccountSerializerTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create()

    def test_create_new(self):
        self.assertEqual(self.organization.homeawayaccount_set.all().count(), 0)
        data = {"username": "user@example.org", "password": "secret123"}
        s = HomeAwayAccountSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        a = s.save(organization=self.organization)

        self.assertEqual(a.username, data["username"])

    def test_update_if_same_username(self):
        data = {"username": "oldusername", "password": "secret123"}
        a = HomeAwayAccount.objects.create(
            organization=self.organization, username=data["username"]
        )
        self.organization.homeawayaccount_set.add(a)
        self.organization.save()
        self.assertEqual(self.organization.homeawayaccount_set.all().count(), 1)

        s = HomeAwayAccountSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        new_a = s.save(organization=self.organization)

        self.assertEqual(a.pk, new_a.pk)


# Models tests


class HomeAwayAccountTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create()
        cls.homeaway = HomeAwayAccount.objects.create(
            organization=cls.organization, username="oldusername"
        )

    def test_service(self):
        service = self.homeaway.service
        self.assertIsInstance(service, home_service.HomeAwayService)

    def test_service_callback(self):
        service = self.homeaway.service
        self.assertTrue(callable(service._auth_callback))
        self.assertEqual(service._auth_callback.__code__.co_argcount, 1)

        self.homeaway.save = MagicMock(return_value=None)
        service.get_session_info = MagicMock(return_value={})
        service._auth_callback(service)
        self.homeaway.save.assert_called_once()
        service.get_session_info.assert_called_once()

    def test_reuse_service_instance(self):
        service1 = self.homeaway.service
        service2 = self.homeaway.service
        self.assertIs(service1, service2)

    def test_update_listings(self):
        self.assertEqual(self.homeaway.listing_set.all().count(), 0)

        with patch.object(self.homeaway, "_service") as m_service:
            m_service.get_host_listings.return_value = [{"data": {}}], {}
            ok = self.homeaway.update_listings()
            self.assertTrue(ok)

            self.assertEqual(self.homeaway.listing_set.all().count(), 1)
            m_service.get_host_listings.assert_called_once()

    def test_update_listings_service_exception(self):
        Listing.objects.create(owner=self.homeaway, data={})

        self.assertEqual(self.homeaway.listing_set.all().count(), 1)

        with patch.object(self.homeaway, "_service") as m_service:
            m_service.get_host_listings.side_effect = ServiceException
            ok = self.homeaway.update_listings()
            self.assertFalse(ok)

            m_service.get_host_listings.assert_called_once()
            self.assertEqual(
                self.homeaway.listing_set.all().count(),
                0,
                msg="Method should've cleared old listings before adding new",
            )

    def test_integration_setting_was_create(self):
        integration_settings_size = IntegrationSetting.objects.filter(
            organization=self.organization, channel_type=self.homeaway.channel_type
        ).count()
        self.assertEqual(integration_settings_size, 1)

    def test_update_listings_commit(self):
        with patch.object(self.homeaway, "save") as m_save, (
            patch.object(self.homeaway, "_service")
        ) as m_service:
            m_service.get_host_listings.return_value = [], {}

            self.homeaway.update_listings()
            m_save.assert_not_called()

            m_save.reset_mock()
            self.homeaway.update_listings(commit=True)
            m_save.assert_called_once()


class ListingsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        organization = Organization.objects.create()
        cls.homeaway = HomeAwayAccount.objects.create(
            organization=organization, data={"username": "oldusername"}
        )

    def test_properties(self):
        data = {"name": "name", "address": "street", "images": [{"url": "url1"}, {"url": "url2"}]}
        listing = Listing.objects.create(owner=self.homeaway, data=data)
        self.assertEqual(listing.name, data["name"])
        self.assertEqual(listing.image, data["images"][0]["url"])
        self.assertEqual(listing.address, data["address"])
        listing.delete()

    def test_properties_empty_data(self):
        listing = Listing.objects.create(owner=self.homeaway, data={})
        self.assertIsNone(listing.name)
        self.assertIsNone(listing.image)
        self.assertIsNone(listing.address)
        listing.delete()

    def test_empty_images_list(self):
        listing = Listing.objects.create(owner=self.homeaway, data={"images": []})
        self.assertIsNone(listing.image)
        listing.delete()


# Views tests


class AccountViewSet(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.username = "username"
        cls.organization = Organization.objects.create()

    def setUp(self):
        self.view = HomeAwayAccountViewSet()

        def _get_serializer(*args, **kwargs):
            return self.view.get_serializer_class()(*args, **kwargs)

        self.view.request = MagicMock()
        self.view.request.user.organization = self.organization
        self.view.get_serializer = MagicMock(side_effect=_get_serializer)

    @property
    def valid_serializer(self):
        serializer = self.view.get_serializer_class()(
            data={"username": self.username, "password": "password"}
        )
        serializer.is_valid()
        return serializer

    @patch("rental_integrations.homeaway.views.HomeAwayService.authenticate")
    def test_login(self, m_authenticate):
        return_value = {"success": True, "status": HTTP_200_OK, "data": {"some": "data"}}
        m_authenticate.return_value = return_value

        status_code, data, session = self.view._login("username", "password")

        m_authenticate.assert_called_with("username", "password")
        self.assertEqual(data, return_value["data"])
        self.assertEqual(status_code, return_value["status"])
        self.assertIsInstance(session, dict)

    @patch("rental_integrations.homeaway.views.HomeAwayService.authenticate")
    def test_login_412(self, m_authenticate):
        return_value = {
            "success": False,
            "status": status.HTTP_412_PRECONDITION_FAILED,
            "data": {},
        }

        m_authenticate.return_value = return_value

        status_code, _, _ = self.view._login("username", "password")

        m_authenticate.assert_called_with("username", "password")
        self.assertEqual(status_code, HTTP_202_ACCEPTED)

    def test_perform_create(self):
        status_code = HTTP_200_OK
        with patch.object(self.view, "_login", return_value=(status_code, {}, {})), (
            patch("rental_integrations.homeaway.views.HomeAwayAccount.update_listings")
        ):
            self.view.perform_create(self.valid_serializer)

        self.skipTest("Turned off for demo")
        homeaway = HomeAwayAccount.objects.get(username=self.username)

        self.assertEqual(homeaway.organization.pk, self.organization.pk)
        self.assertEqual(self.view._status, HTTP_201_CREATED)
        self.assertNotIn("methods", self.view._resp_data)
        self.assertNotIn("phones", self.view._resp_data)
        self.assertIn("listings", self.view._resp_data)
        self.assertEqual(self.view._resp_data["id"], homeaway.pk)
        self.assertEqual(self.view._resp_data["username"], homeaway.username)

    def test_perform_create_2fa_needed(self):
        status_code = HTTP_202_ACCEPTED
        with patch.object(self.view, "_login", return_value=(status_code, {}, {})), (
            patch("rental_integrations.homeaway.views.HomeAwayAccount.update_listings")
        ):
            self.view.perform_create(self.valid_serializer)

        self.skipTest("Turned off for demo")
        homeaway = HomeAwayAccount.objects.get(username=self.username)

        self.assertEqual(homeaway.organization.pk, self.organization.pk)
        self.assertEqual(self.view._status, status_code)
        self.assertIn("methods", self.view._resp_data)
        self.assertIn("phones", self.view._resp_data)
        self.assertIn("listings", self.view._resp_data)
        self.assertEqual(self.view._resp_data["id"], homeaway.pk)
        self.assertEqual(self.view._resp_data["username"], homeaway.username)

    def test_perform_create_error(self):
        status_code = HTTP_400_BAD_REQUEST
        with patch.object(self.view, "_login", return_value=(status_code, {}, {})):
            self.view.perform_create(self.valid_serializer)

        self.skipTest("Turned off for demo")
        self.assertEqual(self.view._status, HTTP_499_NOT_MY_FAULT)
        self.assertIn("error", self.view._resp_data)
        self.assertEqual(HomeAwayAccount.objects.all().count(), 0)

    def test_get_response(self):
        with self.subTest("No _resp_data and _status"):
            self.assertFalse(hasattr(self.view, "_resp_data"))
            self.assertFalse(hasattr(self.view, "_status"))
            self.assertIsNone(self.view.get_response())

        with self.subTest("No _resp_data"):
            self.view._status = HTTP_200_OK
            self.assertFalse(hasattr(self.view, "_resp_data"))
            self.assertTrue(hasattr(self.view, "_status"))
            self.assertIsNone(self.view.get_response())

        with self.subTest("No _status"):
            del self.view._status
            self.view._resp_data = {}
            self.assertTrue(hasattr(self.view, "_resp_data"))
            self.assertFalse(hasattr(self.view, "_status"))
            self.assertIsNone(self.view.get_response())

        with self.subTest("Set _resp_data and _status"):
            resp_status = HTTP_200_OK
            resp_data = {"resp": "data"}

            self.view._status = resp_status
            self.view._resp_data = resp_data
            resp = self.view.get_response()

            self.assertIsInstance(resp, Response)
            self.assertEqual(resp.status_code, resp_status)
            self.assertDictEqual(resp.data, resp_data)


# Service tests


class HomeAwayServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.service = home_service.HomeAwayService(username="username", password="password")

    @patch(
        "rental_integrations.homeaway.service.HomeAwayService._get",
        return_value=MagicMock(ok=False, status_code=499),
    )
    def test_get_host_listings_raises(self, m_get):
        with self.assertRaises(ServiceException):
            self.service.get_host_listings()


class TransformTestCase(TestCase):
    def _to_cozmo_prop(self, data):
        context = {"request": MagicMock(**{"user.organization": None})}
        ser = PropertyCreateSerializer(data=data, context=context)
        self.assertTrue(ser.is_valid(), ser.errors)
        self.assertDictEqual(ser.errors, {})

    def test_minimal(self):
        homeaway_data = {"propertyName": "Some name", "averagePrice": {"value": 100}}
        prop = home_service.to_cozmo_property(homeaway_data)
        self.assertIsInstance(prop, dict)
        self._to_cozmo_prop(prop)

    def test_strip_none(self):
        homeaway_data = {
            "propertyName": "Some name",
            "sleeps": None,
            "averagePrice": {"value": 100},
            "geoCode": {"longitude": None, "latitude": None},
        }
        prop = home_service.to_cozmo_property(homeaway_data)
        self.assertNotIn(None, prop.values())
        self.assertNotIn("coorinates", prop)
        self.assertNotIn("included_guests", prop)
        self._to_cozmo_prop(prop)

    def test_transform(self):
        price = 100
        homeaway_data = {
            "propertyName": "Some name",
            "sleeps": None,
            "averagePrice": {"value": price},
            "geoCode": {"longitude": None, "latitude": None},
            "address": {
                "country": "Some country",
                "stateProvince": "Some state",
                "city": "Some city",
            },
            "refundableDamageDeposit": 300,
        }
        prop = home_service.to_cozmo_property(homeaway_data)
        self.assertEqual(prop["pricing_settings"]["nightly"], price)
        self._to_cozmo_prop(prop)

    def test_rate_None_minimal(self):
        homeaway_data = {
            "propertyName": "Some name",
            "averagePrice": {"value": 100},
            "rateSummary": None,
        }
        prop = home_service.to_cozmo_property(homeaway_data)
        self.assertIsInstance(prop, dict)
        self._to_cozmo_prop(prop)

    def test_rate_minimal(self):
        cleaning_fee = 200
        homeaway_data = {
            "propertyName": "Some name",
            "averagePrice": {"value": 100},
            "rateSummary": {"flatFees": [{"type": "CLEANING_FEE", "maxAmount": cleaning_fee}]},
        }
        prop = home_service.to_cozmo_property(homeaway_data)
        self.assertIsInstance(prop, dict)
        self.assertEqual(prop["pricing_settings"]["cleaning_fee"], cleaning_fee)
        self._to_cozmo_prop(prop)
"""

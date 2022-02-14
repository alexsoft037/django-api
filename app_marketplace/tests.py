import datetime
from secrets import token_urlsafe
from unittest import mock
from urllib.parse import quote_plus

import requests
from django.test import TestCase
from django.urls import reverse
from googleapiclient.errors import HttpError as GoogleHttpError
from oauth2client.client import FlowExchangeError, OAuth2WebServerFlow
from oauth2client.clientsecrets import TYPE_WEB
from rest_framework import status
from rest_framework.exceptions import ValidationError

from accounts.models import Organization
from rental_integrations.airbnb.choices import ReservationStatus
from . import models, serializers, services, views
from .exceptions import SlackError
from .tasks import refresh_airbnb_token

AIRBNB_EXTERNAL_ID = "987"
# models tests


class AppTestCase(TestCase):
    def test__str__(self):
        name = "some name"
        app = models.App(name=name)
        self.assertEqual(str(app), name)


class TagTestCase(TestCase):
    def test__str__(self):
        name = "some name"
        tag = models.Tag(name=name)
        self.assertEqual(str(tag), name)


class BackendAppsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._original_registry = models.backend_apps.registry.copy()
        cls._original_view_names = models.backend_apps.view_names.copy()
        cls.KlassA = type("KlassA", (object,), {})
        cls.KlassB = type("KlassB", (object,), {})

    @classmethod
    def tearDownClass(cls):
        models.backend_apps.registry = cls._original_registry
        models.backend_apps.view_names = cls._original_view_names
        super().tearDownClass()

    def test_backend_apps(self):
        view_name = "some:view"
        self.KlassA()
        with self.subTest(msg="Duplicate key"), self.assertRaises(AssertionError):
            models.backend_apps.registry = {}
            duplicate_key = 0
            models.backend_apps(key=duplicate_key, view_name=view_name)(self.KlassA)
            models.backend_apps(key=duplicate_key, view_name=view_name)(self.KlassB)

        with self.subTest(msg="Invalid key type"):
            models.backend_apps.registry = {}
            for invalid_key in ("key", True, {}, object()):
                with self.assertRaises(AssertionError):
                    models.backend_apps(key=invalid_key, view_name=view_name)(self.KlassA)

        with self.subTest(msg="Correct usage"):
            models.backend_apps.registry = {}
            key_a, key_b = 0, 1

            models.backend_apps(key=key_a, view_name=view_name)(self.KlassA)
            models.backend_apps(key=key_b, view_name=view_name)(self.KlassB)

            self.assertEqual(models.backend_apps.registry[key_a], self.KlassA)
            self.assertEqual(models.backend_apps.registry[key_b], self.KlassB)

    def test_original_backend_apps(self):
        with self.subTest("Only models in registry"):
            self.assertTrue(
                all(
                    issubclass(klass, models.models.Model)
                    for klass in self._original_registry.values()
                )
            )

        with self.subTest("View names are reversible"):
            self.assertTrue(
                all(
                    isinstance(reverse(view_name), str)
                    for view_name in self._original_view_names.values()
                )
            )


# serializers tests


class AirbnbReservationSerializerTestCase(TestCase):
    def test_accept_airbnb_test_listing(self):
        test_listing = serializers.AirbnbReservationSerializer.test_id
        data = {
            "start_date": "2077-12-30",
            "nights": 3,
            "listing_id": test_listing,
            "listing_base_price": "876",
            "number_of_guests": 2,
            "confirmation_code": "code123",
            "total_paid_amount": 100,
            "status_type": ReservationStatus.pending.value,
            "guest_id": "guest123",
            "guest_email": "nick-owme5321y975kcat@guest.airbnb.com",
            "guest_first_name": "Nick",
            "guest_last_name": "Yu",
            "guest_phone_numbers": ["555-555-5555"],
        }
        serializer = serializers.AirbnbReservationSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.save(), serializer._success)

        instance = mock.Mock(id=test_listing, pk=test_listing)
        serializer = serializers.AirbnbReservationSerializer(instance=instance, data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.save(), serializer._success)

    # def test_create_reservation(self):
    #     org = Organization.objects.create()
    #     prop = Property.objects.create(organization=org)
    #     listing = AirbnbSync.objects.create(
    #         prop=prop, external_id=AIRBNB_EXTERNAL_ID, organization=org
    #     )
    #     data = {
    #         "start_date": "2077-12-30",
    #         "booked_at": "2017-12-18T11:50:58+00:00",
    #         "created_at": "2017-12-18T11:50:58+00:00",
    #         "updated_at": "2017-12-18T11:50:58+00:00",
    #         "nights": 3,
    #         "expected_payout_amount_accurate": "100.00",
    #         "cancellation_policy_category": "flexible",
    #         "listing_id": listing.external_id,
    #         "listing_base_price": "876",
    #         "listing_host_fee_accurate": "52.00",
    #         "total_paid_amount_accurate": "100.00",
    #         "number_of_guests": 2,
    #         "confirmation_code": "code123",
    #         "total_paid_amount": 100,
    #         "status_type": ReservationStatus.pending.value,
    #         "guest_id": 123456,
    #         "guest_email": "nick-owme5321y975kcat@guest.airbnb.com",
    #         "guest_first_name": "Nick",
    #         "guest_last_name": "Yu",
    #         "guest_phone_numbers": ["555-555-5555"],
    #         "guest_preferred_locale": "en",
    #         "thread_id": 123,
    #     }
    #
    #     serializer = serializers.AirbnbReservationSerializer(data=data)
    #     self.assertTrue(serializer.is_valid(), serializer.errors)
    #     self.assertEqual(serializer.save(), serializer._success)
    #
    #     reservation = prop.reservation_set.last()
    #     self.assertIsNotNone(reservation.guest)
    #     self.assertIsNotNone(reservation.conversation)


# class AirbnbAvailabilitySerializerTest(TestCase):
#     def test_valid_webhook(self):
#         prop = Property.objects.create()
#         listing = ListingLegacy.objects.create(prop=prop, external_id="987")
#
#         serializer = serializers.AirbnbAvailabilitySerializer(
#             data={
#                 "action": "check_availability",
#                 "start_date": "2018-10-19",
#                 "nights": 3,
#                 "listing_id": listing.external_id,
#             }
#         )
#         self.assertTrue(serializer.is_valid(), serializer.errors)
#         self.assertIn(serializer.save(), (serializer._success, serializer._failure))


class AppSerializerTestCase(TestCase):
    def test_get_installed(self):
        backend_app = 0
        self.assertIn(backend_app, models.backend_apps.registry)

        Model = models.backend_apps.registry[backend_app]
        obj = models.App(backend_app=backend_app)
        serializer = serializers.AppSerializer(
            context={"request": mock.Mock(**{"user.organization.id": 1})}
        )

        with self.subTest(msg="Is installed"), mock.patch.object(
            Model, "objects", mock.Mock(spec=Model.objects)
        ):
            self.assertTrue(serializer.get_installed(obj))

        with self.subTest(msg="Is not installed"):
            self.assertFalse(serializer.get_installed(obj))

        with self.subTest(msg="Is not registered"):
            not_registered = -1
            self.assertNotIn(not_registered, models.backend_apps.registry)
            obj.backend_app = not_registered

            self.assertFalse(serializer.get_installed(obj))

            obj.backend_app = backend_app


class VerifyCodeSerializerTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.code = "some-code"
        cls.state = token_urlsafe()
        cls.serializer = serializers.VerifyCodeSerializer(service=mock.Mock(spec=services.Slack))

    @mock.patch("app_marketplace.serializers.cache.get")
    def test_validate_state(self, m_cache_get):
        args = ("app_marketplace.serializers.Membership.objects",)
        kwargs = {"spec": serializers.Membership.objects, "first.return_value": 2}
        with self.subTest(msg="Valid state"), mock.patch(*args, **kwargs):
            self.serializer.validate_state(self.state)

        with self.subTest(msg="No organization_id"):
            m_cache_get.return_value = None
            with self.assertRaises(ValidationError):
                self.serializer.validate_state(self.state)

    def test_create(self):
        redirect_uri = "https://example.org"
        validated_data = {"code": self.code, "state": self.state, "redirect_uri": redirect_uri}

        self.serializer.create(validated_data=validated_data)
        self.serializer.service.verify_access.assert_called_once_with(
            {"code": self.code, "redirect_uri": redirect_uri}
        )


class SlackAccessSerializerTestCase(TestCase):
    @mock.patch(
        "app_marketplace.serializers.models.SlackApp.objects.create", side_effect=models.SlackApp
    )
    def test_create(self, m_objects):
        validated_data = {
            "access_token": "some-token",
            "team_name": "Team Uno",
            "team_id": "some-id",
            "incoming_webhook": {
                "url": "https://example.org/incoming/hook",
                "channel": "general",
                "configuration_url": "https://example.org/configuration/url",
            },
            "organization_id": 1,
        }
        serializer = serializers.SlackAccessSerializer(data=validated_data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        instance = serializer.save()
        self.assertIsInstance(instance, models.SlackApp)


# services tests


class SlackTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.slack = services.Slack("client_id", "client_secret")

    @mock.patch(
        "app_marketplace.services.requests.request", return_value=mock.Mock(spec=requests.Response)
    )
    def test_call_api(self, m_request):
        method = "get"
        url = "https://example.org"
        kwargs = {"headers": {"Custom-header": "value"}}

        self.slack._call_api(method, url, **kwargs)
        m_request.assert_called_once_with(method, url, timeout=self.slack._http_timeout, **kwargs)
        m_request.return_value.json.assert_called_once()

    @mock.patch("app_marketplace.services.Slack._call_api")
    def test_verify_access(self, m_call_api):
        access_params = {"code": "some-unique-code", "redirect_uri": "https://example.org"}

        with self.subTest(msg="Set default values from settings"):
            slack = services.Slack()
            self.assertGreater(len(slack._client_id), 0)
            self.assertGreater(len(slack._client_secret), 0)

        with self.subTest(msg="Connection timeout"):
            m_call_api.side_effect = requests.Timeout()
            access_data = self.slack.verify_access(access_params)
            self.assertDictEqual(access_data, {})

        with self.subTest(msg="HTTP error"):
            m_call_api.side_effect = requests.HTTPError()
            access_data = self.slack.verify_access(access_params)
            self.assertDictEqual(access_data, {})

    @mock.patch("app_marketplace.services.Slack._call_api")
    def test_send_message(self, m_call_api):
        text = "Hello, Slack"

        with self.subTest(msg="Incorrect `hook_url`"), self.assertRaises(ValueError):
            incorrect_hook_url = "https://incorrect.hook.example.org/yada/yada/"
            self.slack.send_message(incorrect_hook_url, text=text)

        with self.subTest(msg="Hook url does not exist anymore"), self.assertRaises(SlackError):
            m_call_api.side_effect = requests.HTTPError(
                response=mock.Mock(status_code=status.HTTP_404_NOT_FOUND)
            )
            error_hook_url = "https://hooks.slack.com/services/outdated/hook"
            self.slack.send_message(error_hook_url, text=text)

        with self.subTest(msg="Connection timeout"):
            m_call_api.side_effect = requests.Timeout()
            error_hook_url = "https://hooks.slack.com/services/timeout/url"
            ok = self.slack.send_message(error_hook_url, text=text)
            self.assertFalse(ok)

        with self.subTest(msg="Other HTTP error"):
            any_code = status.HTTP_400_BAD_REQUEST  # 404 is a special case
            m_call_api.side_effect = requests.HTTPError(response=mock.Mock(status_code=any_code))
            error_hook_url = "https://hooks.slack.com/services/error/hook"
            self.slack.send_message(error_hook_url, text=text)

        with self.subTest(msg="Message sent Successfully"):
            m_call_api.side_effect = None
            good_hook_url = "https://hooks.slack.com/services/good/hook"
            ok = self.slack.send_message(good_hook_url, text=text)
            self.assertTrue(ok)

    def test_install_url(self):
        state = "some-very-unique-state"
        redirect_uri = "https://example.org/slack/oauth/verify/url"
        install_url = self.slack.install_url(state=state, redirect_uri=redirect_uri)

        self.assertTrue(install_url.startswith("https://"))
        self.assertIn(state, install_url)
        self.assertIn(quote_plus(redirect_uri), install_url)


class GoogleTestCase(TestCase):

    SECRETS = {
        "auth_uri": "https://auth.example.org",
        "token_uri": "https://token.example.org",
        "client_id": "some-id",
        "client_secret": "very-secret",
    }

    class FakeResource:
        def __init__(self, data=None):
            self.data = data or {}

        def userinfo(self):
            return self

        def get(self):
            return self

        def execute(self):
            return self.data

    @classmethod
    def setUpTestData(cls):
        cls.google = services.Google()

    @mock.patch("app_marketplace.services.g_build")
    @mock.patch(
        "app_marketplace.services.flow_from_clientsecrets",
        return_value=mock.Mock(spec=OAuth2WebServerFlow),
    )
    def test_verify_access(self, m_flow, m_g_build):
        access_params = {"code": "some-unique-code", "redirect_uri": "https://example.org"}

        with self.subTest(msg="Access verified"):
            m_g_build.return_value = self.FakeResource({"id": "a"})
            access_data = self.google.verify_access(access_params)
            self.assertIn("user_id", access_data)
            self.assertIn("credentials", access_data)

        with self.subTest(msg="FlowExchange error"):
            m_flow.return_value.step2_exchange.side_effect = FlowExchangeError()
            access_data = self.google.verify_access(access_params)
            self.assertDictEqual(access_data, {})
            m_flow.return_value.step2_exchange.side_effect = None

        with self.subTest(msg="HTTP error"):
            m_g_build.side_effect = GoogleHttpError(status.HTTP_400_BAD_REQUEST, b"Error")
            access_data = self.google.verify_access(access_params)
            self.assertDictEqual(access_data, {})
            m_g_build.side_effect = None

        for msg, value in (("No user id", {"other": "value"}), ("Empty user data", {})):
            with self.subTest(msg=msg):
                m_g_build.return_value = self.FakeResource(value)
                access_data = self.google.verify_access(access_params)
                self.assertDictEqual(access_data, {})

    @mock.patch("oauth2client.client.clientsecrets.loadfile", return_value=(TYPE_WEB, SECRETS))
    def test_install_url(self, m_loadfile):
        state = "some-very-unique-state"
        redirect_uri = "https://example.org/google/oauth/verify/url"
        install_url = self.google.install_url(state=state, redirect_uri=redirect_uri)

        self.assertTrue(install_url.startswith("https://"))
        self.assertIn(state, install_url)
        self.assertIn(quote_plus(redirect_uri), install_url)


# tasks tests


class RefreshAirbnbTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._old_token = "old token"
        cls._new_token = "new token"
        cls._user_id = 123
        cls.airbnb_account = models.AirbnbAccount.objects.create(
            access_token=cls._old_token,
            refresh_token=cls._old_token,
            user_id=cls._user_id,
            organization=Organization.objects.create(),
        )

    def tearDown(self):
        self.airbnb_account.access_token = self._old_token
        self.airbnb_account.refresh_token = self._old_token
        self.airbnb_account.save()

    @mock.patch("app_marketplace.tasks.Airbnb.refresh_token")
    def test_refresh(self, m_refresh_token):
        m_refresh_token.return_value = {
            "access_token": self._new_token,
            "user_id": self._user_id,
            "expires_at": int(datetime.datetime.now().timestamp()),
        }
        refresh_airbnb_token.apply()
        self.airbnb_account.refresh_from_db()

        self.assertEqual(self.airbnb_account.access_token, self._new_token)
        self.assertEqual(self.airbnb_account.refresh_token, self._old_token)

    @mock.patch("app_marketplace.tasks.Airbnb.refresh_token")
    def test_refresh_with_new_refresh_token(self, m_refresh_token):
        m_refresh_token.return_value = {
            "access_token": self._new_token,
            "refresh_token": self._new_token,
            "user_id": self._user_id,
            "expires_at": int(datetime.datetime.now().timestamp()),
        }
        refresh_airbnb_token.apply()
        self.airbnb_account.refresh_from_db()

        self.assertEqual(self.airbnb_account.access_token, self._new_token)
        self.assertEqual(self.airbnb_account.refresh_token, self._new_token)

    @mock.patch("app_marketplace.tasks.Airbnb.refresh_token")
    def test_fail_fetching_new_token(self, m_refresh_token):
        m_refresh_token.side_effect = requests.RequestException
        refresh_airbnb_token.apply()
        self.airbnb_account.refresh_from_db()

        self.assertEqual(self.airbnb_account.access_token, self._old_token)
        self.assertEqual(self.airbnb_account.refresh_token, self._old_token)


# views tests


class OAuth2ViewSetTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.request = mock.Mock(
            **{"user.id": 1, "_request.build_absolute_uri.return_value": "https://example.org"}
        )
        cls.view = views.OAuth2ViewSet(request=cls.request, format_kwarg=None)
        cls.view.get_serializer_class = mock.Mock(side_effect=serializers.GoogleAccessSerializer)
        cls.view.service_class = mock.Mock(
            spec=services.Google,
            **{"CACHE_KEY": "cache_key", "install_url.return_value": "https://example.org"}
        )

    def test_list(self):
        resp = self.view.list(self.request)
        self.view.service_class.install_url.assert_called_once()
        self.assertIn("url", resp.data)
        self.assertEqual(len(resp.data), 1)

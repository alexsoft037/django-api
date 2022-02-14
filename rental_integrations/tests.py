from decimal import Decimal
from unittest import mock

from django.test import TestCase
from requests import RequestException
from rest_framework import mixins

from cozmo_common.filters import OrganizationFilter
from . import models, views
from .exceptions import ServiceException
from .filters import ChannelFilter
from .service import BaseService, RentalAPIClient
from .tools import strip_falsy


# Models tests


class BaseAccountTestCase(TestCase):
    def test_interface(self):
        account = models.BaseAccount()
        fake_arg = None

        for method in (
            "service",
            "update_listings",
            "update_reservations",
            "import_listings",
            "import_reservations",
        ):
            with self.assertRaises(NotImplementedError):
                getattr(account, method)(fake_arg)


class BaseListingTestCase(TestCase):
    def test_interface(self):
        listing = models.BaseListing(data={}, owner=None)

        for method in ("external_id", "name", "image", "address", "channel_type"):
            with self.assertRaises(NotImplementedError):
                getattr(listing, method)()


# Views tests


class IntegrationViewSetTestCase(TestCase):
    def test_has_endpoints(self):
        self.assertTrue(
            all(
                (
                    issubclass(views.IntegrationViewSet, mixins.CreateModelMixin),
                    issubclass(views.IntegrationViewSet, mixins.RetrieveModelMixin),
                    issubclass(views.IntegrationViewSet, mixins.DestroyModelMixin),
                    issubclass(views.IntegrationViewSet, mixins.ListModelMixin),
                )
            )
        )
        self.assertTrue(hasattr(views.IntegrationViewSet, "fetch"))
        self.assertEqual(views.IntegrationViewSet.import_listings.__dict__["url_path"], "import")
        self.assertEqual(views.IntegrationViewSet.update_listings.__dict__["url_path"], "listings")

        with self.assertRaises(NotImplementedError):
            request, pk = None, None
            views.IntegrationViewSet.update_listings(self, request, pk)

    def test_filter_backends(self):
        self.assertIn(OrganizationFilter, views.IntegrationViewSet.filter_backends)


class IntegrationSettingViewSetTestCase(TestCase):
    def test_filter_backends(self):
        self.assertIn(OrganizationFilter, views.IntegrationSettingViewSet.filter_backends)

    def test_has_endpoints(self):
        self.assertTrue(
            all(
                (
                    issubclass(views.IntegrationSettingViewSet, mixins.RetrieveModelMixin),
                    issubclass(views.IntegrationSettingViewSet, mixins.UpdateModelMixin),
                    issubclass(views.IntegrationSettingViewSet, mixins.ListModelMixin),
                )
            )
        )


# Services tests


class BaseServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.service = BaseService(username="username", password="password")

    def test_auth_callback_dummy(self):
        some_arg = "some arg"
        self.assertIsNone(self.service._dummy_callback(some_arg))
        self.assertIsNone(self.service._dummy_callback(service=some_arg))

    def test_auth_callback_requirements(self):
        kwargs = {"username": "username", "password": "password"}

        def _too_few_args():
            pass

        def _too_many_args(a, b):
            pass

        _not_callable = "not callable"

        with self.assertRaises(ValueError):
            BaseService(**kwargs, auth_callback=_too_few_args)

        with self.assertRaises(ValueError):
            BaseService(**kwargs, auth_callback=_too_many_args)

        with self.assertRaises(ValueError):
            BaseService(**kwargs, auth_callback=_not_callable)

    def test_interface(self):
        srv = self.service

        self.assertRaises(NotImplementedError, srv.authenticate, "username", "password")
        self.assertRaises(NotImplementedError, srv.format_path, "path", {"path": "kwargs"})
        self.assertRaises(NotImplementedError, srv.get_headers, headers={"some": "params"})
        self.assertRaises(
            NotImplementedError, srv.get_host_listings, offset=0, limit=50, has_availability=False
        )
        self.assertRaises(NotImplementedError, srv.get_params)
        self.assertRaises(NotImplementedError, srv.get_session_info)
        self.assertRaises(NotImplementedError, srv.need_to_auth, "resp")

    def test_http_methods(self):
        path = "/some/url"

        with mock.patch.object(self.service, "_request") as m_req:
            self.service._get(path)
            m_req.assert_called_once_with(path, method="get")

        with mock.patch.object(self.service, "_request") as m_req:
            self.service._post(path)
            m_req.assert_called_once_with(path, method="post")

        with mock.patch.object(self.service, "_request") as m_req:
            self.service._put(path)
            m_req.assert_called_once_with(path, method="put")

    def test_make_request_unsupported(self):
        with self.assertRaises(ValueError):
            self.service._make_request("invalid_method", "http://example.org")

    # @mock.patch("rental_integrations.service.requests.request", side_effect=RequestException)
    # def test_make_request_exception(self, m_get):
    #     url = "http://example.org"
    #     data = None
    #     with self.assertLogs("cozmo", level=logging.ERROR) as logger:
    #         resp = self.service._make_request("get", url, data=data)
    #
    #     self.assertEqual(len(logger.output), 1)
    #     self.assertIn(url, logger.output[0])
    #
    #     self.assertFalse(resp.ok)
    #     self.assertEqual(resp.status_code, HTTP_499_NOT_MY_FAULT)
    #     self.assertEqual(resp.url, url)
    #     m_get.assert_called_once_with("get", url, data=data, timeout=self.service.timeout)


class RentalAPIClientTestCase(TestCase):
    def test_get_headers(self):
        self.assertDictEqual(RentalAPIClient.get_headers(self, context={}), {})

    @mock.patch("rental_integrations.service.requests.request")
    def test_call_api(self, m_request):
        auth = None
        data = b""
        headers = {}
        kwargs = {
            "_authenticate.return_value": auth,
            "_parse_data.return_value": data,
            "_call_api": RentalAPIClient._call_api,
            "_http_methods": RentalAPIClient._http_methods,
            "get_headers.return_value": headers,
        }
        with mock.patch(
            "rental_integrations.tests.RentalAPIClient", spec=RentalAPIClient, **kwargs
        ):
            client = RentalAPIClient("user", "secret")

        url = "https://example.org"

        with self.subTest(msg="HTTP method defaults to POST"):
            m_request.reset_mock()
            client._call_api(client, url, data)
            m_request.assert_called_once_with(
                "post", url, data=data, headers=headers, auth=auth, timeout=client.timeout
            )

        with self.subTest(msg="Call chosen HTTP method"):
            method = "GET"
            m_request.reset_mock()
            client._call_api(client, url, data, http_method=method)
            m_request.assert_called_once_with(
                method.lower(), url, data=data, headers=headers, auth=auth, timeout=client.timeout
            )

        with self.subTest(msg="Invalid method"), self.assertRaises(ValueError):
            client._call_api(client, url, data, http_method="Invalid")

        with self.subTest(msg="Connection error"):
            m_request.reset_mock()
            status_code = 401
            content = b"Auth needed"
            m_request.side_effect = RequestException(
                response=mock.MagicMock(status_code=status_code, content=content)
            )
            ret_code, ret_content = client._call_api(client, url, None)
            self.assertEqual(ret_code, status_code)
            self.assertEqual(ret_content, content)


# Exceptions tests


class ServiceExceptionTestCase(TestCase):
    def test_custom_attrs(self):
        data = {"key": "value", "other": 1}
        e = ServiceException(**data)
        for k, v in data.items():
            with self.subTest(key=k):
                self.assertEqual(getattr(e, k), v)


class StripFalsyTestCase(TestCase):
    def test_strip_falsy(self):
        with self.subTest(msg="All falsy"):
            stripped = strip_falsy(
                {
                    "l1": [],
                    "l2": [None],
                    "l3": [None, None, None],
                    "t1": (),
                    "t2": (None,),
                    "t3": (None, None),
                    "d1": {},
                    "d2": {"k1": ""},
                    "d3": {"k1": None, "k2": None},
                    "n1": None,
                    "s1": "",
                }
            )
            self.assertDictEqual(stripped, {})

        with self.subTest(msg="All truthy"):
            truthy = {
                "l1": [1, 2],
                "l2": [True, False],
                "t1": (True,),
                "t2": ("text", 0),
                "d1": {"k1": "text"},
                "d2": {"k1": False, "k2": 1},
                "d3": {"k1": False, "k2": None},
                "s1": "text",
                "b1": False,
                "b2": True,
                "g1": (i for i in range(0)),
                "g2": (i for i in range(10)),
                "D1": Decimal("0"),
                "D2": Decimal("1.0"),
            }
            stripped = strip_falsy(truthy)
            self.assertDictEqual(stripped, truthy)


# Filters tests


class ChannelFilterTestCase(TestCase):
    def names_cant_have_dash(self):
        for name in ChannelFilter.names_to_props.keys():
            with self.subTest(name):
                self.assertNotIn("-", name)

    # def test_filter_queryset(self):
    #     channel_filter = ChannelFilter()
    #     test_channel = "test"
    #     test_prop_name = "test_prop_name"
    #     channel_filter.names_to_props = {test_channel: test_prop_name}
    #     view = mock.Mock()

        # with self.subTest("Props exported to channel"):
        #     request = mock.Mock(query_params={"channel": test_channel})
        #     queryset = mock.Mock()
        #     channel_filter.filter_queryset(request, queryset, view)
        #     queryset.exclude.assert_called_once_with(test_prop_name=None)

        # with self.subTest("Props not exported to channel"):
        #     request = mock.Mock(query_params={"channel": f"-{test_channel}"})
        #     queryset = mock.Mock()
        #     channel_filter.filter_queryset(request, queryset, view)
        #     queryset.filter.assert_called_once_with(test_prop_name=None)

        # with self.subTest("Do not filter props"):
        #     request = mock.Mock(query_params={})
        #     queryset = mock.Mock()
        #     channel_filter.filter_queryset(request, queryset, view)
        #     queryset.filter.assert_not_called()
        #     queryset.exclude.assert_not_called()

import json
from functools import reduce
from operator import or_
from unittest import mock

from django.test import TestCase

from . import serializers
from .mappers import Mapper
from .models import YelpCategories

YELP_RESP = """[
    {
        "alias": "3dprinting",
        "title": "3D Printing",
        "parents": [
            "localservices"
        ]
    },
    {
        "alias": "localservices",
        "title": "Local Services",
        "parents": []
    },
    {
        "alias": "absinthebars",
        "title": "Absinthe Bars",
        "parents": [
            "bars"
        ]
    },
    {
        "alias": "bars",
        "title": "Bars",
        "parents": [
            "nightlife"
        ]
    },
    {
        "alias": "nightlife",
        "title": "Nightlife",
        "parents": []
    }
]
"""


class YelpCategoriesTestCase(TestCase):
    def setUp(self):
        self.response = mock.MagicMock(**{"json.return_value": json.loads(YELP_RESP)})
        self.m_request_get = mock.patch("requests.get", return_value=self.response)

    def tearDown(self):
        YelpCategories.objects.all().delete()

    def test_fetch(self):
        with self.m_request_get:
            self.assertEqual(YelpCategories.objects.count(), 0)
            YelpCategories.fetch()
            self.assertEqual(YelpCategories.objects.count(), 5)

            with self.subTest(msg="New Fetch will not create new objects"):
                YelpCategories.fetch()
                self.assertEqual(YelpCategories.objects.count(), 5)

    def test_get_parent_category(self):
        with self.m_request_get:
            YelpCategories.fetch()
            self.assertEqual(
                YelpCategories.get_parent_category("3dprinting"), Mapper.others.filter
            )
            self.assertEqual(
                YelpCategories.get_parent_category("localservices"), Mapper.others.filter
            )
            self.assertIn(
                YelpCategories.get_parent_category("absinthebars"), Mapper.categories.keys()
            )


class YelpSerializerTestMixin:
    def serializer_create(self):
        serializer = self.serializer_class()
        serializer.TASK_EXPIRE = 0.001
        type(serializer).data = mock.PropertyMock()

        validated_data = {}
        return serializer.create(validated_data)


class YelpAutocompleteSerializerTestCase(YelpSerializerTestMixin, TestCase):

    serializer_class = serializers.YelpAutocompleteSerializer

    @mock.patch("pois.serializers.YelpBaseSerializer.create", return_value=[])
    def test_task_expires(self, _):
        businesses = self.serializer_create()
        self.assertEqual(businesses, [])


class YelpTopPlacesSerializerTestCase(YelpSerializerTestMixin, TestCase):

    serializer_class = serializers.YelpTopPlacesSerializer

    @mock.patch(
        "pois.serializers.YelpTopPlacesSerializer._get_businesses",
        return_value=[{c: {}} for c in Mapper.categories.values()],
    )
    def test_task_expires(self, _):
        businesses = self.serializer_create()
        self.assertTrue(businesses)
        self.assertFalse(
            reduce(or_, map(bool, businesses.values())), "All values should be empty lists"
        )

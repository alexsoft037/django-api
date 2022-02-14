# from unittest import mock
#
# from django.test import TestCase
# from rest_framework.exceptions import ValidationError
#
# from accounts.models import Organization
# from . import models, service, service_serializers
#
#
# class CamelizeTestCase(TestCase):
#     def test_camelize(self):
#         simple_key = "key"
#         camel_key = "camelCase"
#         nested_key = "nested"
#         underscore_key = "underscore_case"
#         new_key = "underscoreCase"
#         list_key = "list"
#
#         nested = {simple_key: 0, camel_key: 1, underscore_key: 2}
#
#         original = {
#             simple_key: ["some_value", "OtherValue", "another value"],
#             camel_key: "some_snake_case_value",
#             underscore_key: "some_value",
#             nested_key: nested,
#             list_key: [nested],
#         }
#
#         camelized = service_serializers.camelize(original)
#
#         self.assertIsNot(original, camelized)
#
#         self.assertIn(simple_key, camelized)
#         self.assertListEqual(camelized[simple_key], original[simple_key])
#
#         self.assertIn(camel_key, camelized)
#         self.assertEqual(camelized[camel_key], original[camel_key])
#
#         self.assertNotIn(underscore_key, camelized)
#         self.assertIn(new_key, camelized)
#         self.assertEqual(camelized[new_key], original[underscore_key])
#
#         self.assertIn(nested_key, camelized)
#         self.assertIn(simple_key, camelized[nested_key])
#         self.assertIn(camel_key, camelized[nested_key])
#         self.assertIn(new_key, camelized[nested_key])
#
#         self.assertCountEqual(camelized[list_key], original[list_key])
#         self.assertIn(simple_key, camelized[list_key][0])
#         self.assertIn(camel_key, camelized[list_key][0])
#         self.assertIn(new_key, camelized[list_key][0])
#
#
# class UnderscoreizeTestCase(TestCase):
#     def test_underscoreize(self):
#         simple_key = "key"
#         camel_key = "camelCase"
#         nested_key = "nested"
#         underscore_key = "underscore_case"
#         new_key = "camel_case"
#         list_key = "list"
#
#         nested = {simple_key: 0, camel_key: 1, underscore_key: 2}
#
#         original = {
#             simple_key: ["some_value", "OtherValue", "another value"],
#             camel_key: "someCamelCaseValue",
#             underscore_key: "some_value",
#             nested_key: nested,
#             list_key: [nested],
#         }
#
#         underscoreized = service_serializers.underscoreize(original)
#
#         self.assertIsNot(original, underscoreized)
#
#         self.assertIn(simple_key, underscoreized)
#         self.assertListEqual(underscoreized[simple_key], original[simple_key])
#
#         self.assertNotIn(camel_key, underscoreized)
#         self.assertIn(new_key, underscoreized)
#         self.assertEqual(underscoreized[new_key], original[camel_key])
#
#         self.assertIn(underscore_key, underscoreized)
#         self.assertEqual(underscoreized[underscore_key], original[underscore_key])
#
#         self.assertIn(nested_key, underscoreized)
#         self.assertIn(simple_key, underscoreized[nested_key])
#         self.assertIn(new_key, underscoreized[nested_key])
#         self.assertIn(underscore_key, underscoreized[nested_key])
#
#         self.assertCountEqual(underscoreized[list_key], original[list_key])
#         self.assertIn(simple_key, underscoreized[list_key][0])
#         self.assertIn(new_key, underscoreized[list_key][0])
#         self.assertIn(underscore_key, underscoreized[list_key][0])
#
#
# class DetilSerializerTestCase(TestCase):
#     @classmethod
#     def setUpTestData(cls):
#         cls.serializer = service_serializers.DetailSerializer()
#
#     def test_validate_studio(self):
#         with self.subTest(msg="Bedroom in studio"), self.assertRaises(ValidationError):
#             data = {
#                 "property_type": service_serializers.DetailSerializer._studio_type,
#                 "bedrooms": [{"ordinal": 1}],
#             }
#             self.serializer.validate(data)
#
#         with self.subTest(msg="Sleeping area in studio"):
#             data = {
#                 "property_type": service_serializers.DetailSerializer._studio_type,
#                 "bedrooms": [{"ordinal": 0}],
#             }
#             self.assertDictEqual(self.serializer.validate(data), data)
#
#     def test_validate_not_studio(self):
#         with self.subTest(msg="Only sleeping area"), self.assertRaises(ValidationError):
#             data = {"property_type": "not-studio", "bedrooms": [{"ordinal": 0}]}
#             self.serializer.validate(data)
#
#         with self.subTest(msg="Sleeping area and bedroom"):
#             data = {"property_type": "not-studio", "bedrooms": [{"ordinal": 0}, {"ordinal": 1}]}
#             self.assertDictEqual(self.serializer.validate(data), data)
#
#         with self.subTest(msg="No bedrooms data"):
#             data = {"property_type": "not-studio"}
#             self.assertDictEqual(self.serializer.validate(data), data)
#
#
# class TripAdvisorAccountTestCase(TestCase):
#     @classmethod
#     def setUpTestData(cls):
#         organization = Organization.objects.create()
#         cls.account = models.TripAdvisorAccount.objects.create(
#             username="ta_username", organization=organization
#         )
#
#     def test_channel_type(self):
#         self.assertEqual(self.account.channel_type, "TripAdvisor")
#
#     @mock.patch("rental_integrations.trip_advisor.models.TripAdvisorClient.get_listings")
#     def test_update_listings(self, m_get_listings):
#
#         with self.subTest(msg="Pull failed"):
#             m_get_listings.return_value = (400, None)
#
#             self.assertFalse(self.account.update_listings())
#
#         with self.subTest(msg="Sucessful pull"):
#             data = {"some": "data"}
#             self.account.listing_set.add(
#                 models.Listing.objects.create(owner=self.account, data=None)
#             )
#             m_get_listings.return_value = (200, [data])
#
#             self.assertTrue(self.account.update_listings())
#             with self.assertRaises(models.Listing.DoesNotExist):
#                 self.account.listing_set.get(data=None)
#             self.assertTrue(self.account.listing_set.filter(data=data).exists())
#
#
# class TripAdvisorServiceTestCase(TestCase):
#     @classmethod
#     def setUpTestData(cls):
#         cls.ta = service.TripAdvisorClient("user", "secret")
#
#     def test_netloc(self):
#         self.assertTrue(self.ta.netloc.endswith("/"))
#
#     def test_get_listings(self):
#         listing_id = 123
#
#         with mock.patch.object(self.ta, "_call_api", return_value=(400, None)) as m_call_api:
#             self.ta.get_listing(listing_id)
#             m_call_api.assert_called_once()
#             url, *_ = m_call_api.call_args[0]
#             valid_url = f"{self.ta.netloc}{self.ta._user}/{listing_id}"
#             self.assertEqual(url, valid_url)

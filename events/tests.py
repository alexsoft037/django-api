# from django.contrib.auth import get_user_model
# from django.test import TestCase
#
# from accounts.models import Organization
# from crm.models import Contact
# from listings.models import Property, Reservation
# from .choices import EventType
# from .models import Event
# from .serializers import ReservationEventSerializer
#
# User = get_user_model()
#
#
# class ReservationEventSerializerTest(TestCase):
#     @classmethod
#     def setUpTestData(cls):
#         user = User.objects.create(first_name="Jack", username="jack@samurai.com")
#         organization = Organization.objects.create()
#         cls.event = Event.objects.create(
#             event_type=EventType.Message_sent,
#             context={"request_user_id": user.id},
#             organization=organization,
#             content_object=Reservation.objects.create(
#                 start_date="2018-10-10",
#                 end_date="2018-12-12",
#                 price=100,
#                 paid=100,
#                 guest=Contact.objects.create(
#                     first_name="Genndy",
#                     email="genndy.tartakovsky@example.com",
#                     organization=organization,
#                 ),
#                 prop=Property.objects.create(),
#             ),
#         )
#
#     def setUp(self):
#         self.serializer = ReservationEventSerializer(instance=self.event)
#         self.event.refresh_from_db()
#
#     def test_get_name(self):
#         with self.subTest("User exists"):
#             self.assertIsInstance(self.serializer.get_name(self.event), str)
#
#         with self.subTest("User does not exist"):
#             self.event.context["request_user_id"] = None
#             self.assertIsInstance(self.serializer.get_name(self.event), str)
#
#     def test_get_guest_name(self):
#         with self.subTest("Guest with firstname"):
#             self.assertIsInstance(self.serializer.get_guest_name(self.event), str)
#
#         with self.subTest("Guest without firstname"):
#             self.event.content_object.guest.first_name = ""
#             self.assertIsInstance(self.serializer.get_guest_name(self.event), str)
#
#         with self.subTest("Guest does not exist"):
#             self.event.content_object.guest = None
#             self.assertIsInstance(self.serializer.get_name(self.event), str)
#
#     def test_get_category(self):
#         category = self.serializer.get_category(self.event)
#         self.assertEqual(category, self.event.content_object._meta.model_name)

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Membership, Organization, Token
from crm.models import Contact
from listings.models import Property, Reservation
from send_mail.models import Conversation, Message


class SearchTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        today = date.today()
        cls.user = User.objects.create(
            username="test",
            first_name="some first name",
            last_name="some last name",
            is_superuser=True,
        )
        Membership.objects.create(
            organization=Organization.objects.create(), user=cls.user, is_default=True
        )
        cls.token = Token.objects.create(
            name="user_token", user=cls.user, organization=cls.user.organization
        )
        cls.client = APIClient()
        cls.client.credentials(HTTP_AUTHORIZATION="Token: {}".format(cls.token.generate_key()))
        cls.property = Property.objects.create(
            name="some property",
            rental_type=Property.Rentals.Entire_Home.value,
            property_type=Property.Types.Condo.value,
            organization=cls.user.organization,
        )
        cls.contact = Contact.objects.create(
            first_name="some first name",
            last_name="some last name",
            email="email@example.org",
            organization=cls.user.organization,
        )
        cls.reservation = Reservation.objects.create(
            start_date=today,
            end_date=today + timedelta(days=2),
            base_total="100.00",
            price="100.00",
            paid="0.00",
            prop=cls.property,
            guest=cls.contact,
        )
        cls.conversation = Conversation.objects.create(reservation=cls.reservation)
        cls.message = Message.objects.create(
            subject="some object",
            text="some text", sender=cls.user, conversation=cls.conversation, type=5
        )

    def test_search(self):
        response = self.client.get(
            "/search/?q=some", HTTP_AUTHORIZATION="Token: {}".format(self.token.generate_key())
        )
        contacts = response.data.get("contacts")
        # conversation_threads = response.data.get("conversation_threads")
        reservations = response.data.get("reservations")
        properties = response.data.get("properties")

        self.assertEqual(len(contacts), 1)
        # self.assertEqual(len(conversation_threads), 1)
        self.assertEqual(len(reservations), 1)
        self.assertEqual(len(properties), 1)

        self.assertListEqual(
            list(contacts[0].keys()),
            [
                "id",
                "first_name",
                "last_name",
                "email",
                "secondary_email",
                "phone",
                "secondary_phone",
                "url",
            ],
        )
        self.assertListEqual(
            list(properties[0].keys()), ["id", "name", "full_address", "cover_image", "url"]
        )
        self.assertListEqual(
            list(reservations[0].keys()),
            [
                "id",
                "prop",
                "guest",
                "guests_adults",
                "guests_children",
                "guests_infants",
                "start_date",
                "end_date",
                "source",
                "pets",
                "status",
                "dynamic_status",
                "price",
                "base_total",
                "nightly_price",
                "currency",
                "url",
            ],
        )
        # self.assertListEqual(
        #     list(conversation_threads[0].keys()),
        #     ["id", "guest_name", "guest_photo", "reservation"],
        # )

        self.assertEqual(contacts[0].get("id"), self.contact.id)
        self.assertEqual(properties[0].get("id"), self.property.id)
        self.assertEqual(reservations[0].get("id"), self.reservation.id)
        # self.assertEqual(conversation_threads[0].get("id"), self.mail.id)

    def test_with_empty_search(self):
        response = self.client.get(
            "/search", HTTP_AUTHORIZATION="Token: {}".format(self.token.generate_key())
        )
        contacts = response.data.get("contacts")
        conversation_threads = response.data.get("conversation_threads")
        reservations = response.data.get("reservations")
        properties = response.data.get("properties")

        self.assertEqual(len(contacts), 0)
        self.assertEqual(len(conversation_threads), 0)
        self.assertEqual(len(reservations), 0)
        self.assertEqual(len(properties), 0)

"""
import io
import math
from datetime import date, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.status import HTTP_201_CREATED

from accounts.models import Membership, Organization
from app_marketplace.models import AirbnbApp
from cozmo_common.filters import OrganizationFilter
from crm.models import Contact
from listings.models import (
    Availability,
    BookingSettings,
    CheckInOut,
    ListingDescriptions,
    Location,
    Property,
    Reservation,
)
from . import mappers, models, serializers, views

User = get_user_model()


class IsFromVoyajoyTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.perm = views.IsFromVoyajoy()

    def test_has_permission(self):
        view = None

        valid_mails = ("mail@voyajoy.com", "mail@subdomain.voyajoy.com")
        for mail in valid_mails:
            user = mock.MagicMock(email=mail)
            request = mock.MagicMock(user=user)
            with self.subTest(mail=mail, msg="Should have permission"):
                self.assertTrue(self.perm.has_permission(request, view))

        invalid_mails = ("mail@vojayoj.co.uk", "mail@example.com", "mail@voyajot.com")
        for mail in invalid_mails:
            user = mock.MagicMock(email=mail)
            request = mock.MagicMock(user=user)
            with self.subTest(mail=mail, msg="Should not have permission"):
                self.assertFalse(self.perm.has_permission(request, view))


class TagListingFieldTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.field = serializers.TagListingField()
        cls.field.queryset = mock.MagicMock(
            spec=serializers.TagListingField.queryset, **{"get.return_value": models.Tag()}
        )

    def test_to_internal_value(self):
        with self.subTest("Non-integer string"), self.assertRaises(ValidationError):
            data = "not integer"
            self.field.to_internal_value(data)

        with self.subTest("Invalid type instead int"), self.assertRaises(ValidationError):
            data = {"id": "12"}
            self.field.to_internal_value(data)

        with self.subTest("Integer-like id"):
            for data in (b"123", "123", 321):
                self.assertIsInstance(self.field.to_internal_value(data), models.Tag)

        with self.subTest("No such tag"), self.assertRaises(ValidationError):
            self.field.queryset.get.side_effect = ValidationError
            data = 987
            self.assertIsInstance(self.field.to_internal_value(data), models.Tag)


class FileListSerializerTestCase(TestCase):
    def test_validate_files(self):
        Klass = serializers.FileListSerializer
        ser = Klass()

        with self.subTest(msg="Total size too big"):
            too_much = math.ceil(Klass.MAX_TOTAL / Klass.MAX_FILE)
            files = (mock.MagicMock(size=Klass.MAX_FILE + 1) for i in range(too_much))
            self.assertRaises(ValidationError, ser.validate_files, files)

        with self.subTest(msg="Valid files"):
            ok_size = math.floor(Klass.MAX_TOTAL / Klass.MAX_FILE)
            files = [mock.MagicMock(size=Klass.MAX_FILE - 1) for i in range(ok_size)]
            self.assertListEqual(ser.validate_files(files), files)


class MailSerializerTestCase(TestCase):
    serializer_class = serializers.MailSerializer

    @classmethod
    def setUpTestData(cls):
        today = date.today()
        cls.user = User.objects.create()
        cls.user.organization = Organization.objects.create()
        prop = Property.objects.create(
            name="Some name",
            rental_type=Property.Rentals.Entire_Home.value,
            property_type=Property.Types.Condo.value,
            organization=cls.user.organization,
        )
        contact = Contact.objects.create(
            first_name="Bob",
            last_name="Rob",
            email="email@example.org",
            organization=cls.user.organization,
        )
        cls.reservation = Reservation.objects.create(
            start_date=today,
            end_date=today + timedelta(days=2),
            price="100.00",
            paid="0.00",
            prop=prop,
            guest=contact,
        )
        cls.serializer_data = {
            "receiver": "luke@example.com",
            "text": "Join me",
            "subject": "I am your father",
            "reservation": cls.reservation.pk,
        }

    def test_validate(self):
        ser = self.serializer_class()

        self.assertRaises(ValidationError, ser.validate, {"user": None})

        with self.subTest(msg="User not in Organization"):
            org = self.user.organization
            self.user.organization = None
            data = {"user": self.user, "reservation_id": 1}
            self.assertRaises(ValidationError, ser.validate, data)
            self.user.organization = org

        with self.subTest(msg="Reservation does not exist"), (
            mock.patch(
                "send_mail.serializers.Reservation.objects.filter", side_effect=ObjectDoesNotExist
            )
        ):
            data = {"user": self.user, "reservation_id": 1}
            self.assertRaises(ValidationError, ser.validate, data)

        with self.subTest(msg="Invalid mail variable"), (
            mock.patch("send_mail.serializers.Reservation.objects.filter")
        ), (mock.patch("send_mail.mappers.Mapper.substitute", side_effect=ValueError("boo"))):
            data = {"user": self.user, "reservation_id": 1, "text": ""}
            self.assertRaises(ValidationError, ser.validate, data)

    def test_save(self):
        ser = self.serializer_class(
            data=self.serializer_data, context={"request": mock.MagicMock(user=self.user)}
        )
        self.assertTrue(ser.is_valid(), ser.errors)
        with mock.patch("send_mail.serializers.EmailMultiAlternatives.send") as m_send:
            ser.create(ser.validated_data)
            m_send.assert_called_once()

        with mock.patch(
            "send_mail.serializers.EmailMultiAlternatives.send", side_effect=TypeError
        ), self.assertRaises(ValidationError):
            ser.create(ser.validated_data)

        with mock.patch(
            "send_mail.serializers.EmailMultiAlternatives.send", side_effect=Exception
        ), self.assertRaises(ValidationError):
            ser.create(ser.validated_data)

        with self.subTest(msg="Send attachments"), mock.patch(
            "send_mail.serializers.EmailMultiAlternatives.send"
        ):
            attachment = io.BytesIO(b"some content")
            attachment.name = "some name"
            validated_data = {"attachments": [attachment], **ser.validated_data}
            mail = ser.create(validated_data)
            self.assertEqual(mail.attachment_set.count(), 1)


class AirbnbMessageSerializerTestCase(MailSerializerTestCase):

    serializer_class = serializers.AirbnbMessageSerializer

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.serializer_data["thread_id"] = 12
        AirbnbApp.objects.create(
            access_token="access",
            refresh_token="refresh",
            organization=cls.user.organization,
            user_id=123,
        )

    @mock.patch("send_mail.serializers.AirbnbService.push_message")
    def test_save(self, m_push_message):
        serializer = self.serializer_class(
            data=self.serializer_data, context={"request": mock.MagicMock(user=self.user)}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        m_push_message.assert_called_once()


class MailViewTestCase(TestCase):
    @mock.patch("send_mail.views.MailView.get_serializer")
    def test_create(self, m_get_ser):
        view = views.MailView()

        data = {"data.getlist.return_value": []}
        view.request = mock.MagicMock(**data)
        m_ser = m_get_ser.return_value

        resp = view.create(view.request)

        m_ser.is_valid.assert_called_once()
        m_ser.save.assert_called_once()
        self.assertEqual(resp.status_code, HTTP_201_CREATED)

    def test_get_serializer(self):
        view = views.MailView()
        airbnb_key = "user.organization.airbnbapp_set.exists.return_value"
        google_key = "user.organization.googleapp_set.exists.return_value"

        with self.subTest("Use AirbnbMessageSerializer"):
            view.request = mock.MagicMock(**{airbnb_key: True, google_key: True})
            self.assertIs(view.get_serializer_class(), serializers.AirbnbMessageSerializer)

        with self.subTest("Use GmailSerializer"):
            view.request = mock.MagicMock(**{airbnb_key: False, google_key: True})
            self.assertIs(view.get_serializer_class(), serializers.GmailSerializer)

        with self.subTest("Use MailSerializer"):
            view.request = mock.MagicMock(**{airbnb_key: False, google_key: False})
            self.assertIs(view.get_serializer_class(), serializers.MailSerializer)


class MapperTestCase(TestCase):
    def setUp(self):
        self.reservation.guest.refresh_from_db()
        self.reservation.prop.refresh_from_db()
        self.reservation.refresh_from_db()

    @classmethod
    def setUpTestData(cls):
        cls.today = date.today()
        organization = Organization.objects.create()
        cls.user = User.objects.create(
            first_name="Agent Name", email="agent@example.org", phone="+1999999999"
        )
        cleaner = User.objects.create(
            username="Cleaner",
            first_name="Cleaner Name",
            email="cleaner@example.org",
            phone="+1999999998",
            account_type=User.VendorTypes.Cleaner.value,
        )

        Membership.objects.bulk_create(
            Membership(user=user, organization=organization, is_default=True)
            for user in (cls.user, cleaner)
        )

        location = Location.objects.create(
            continent="Europe",
            country="Poland",
            region="Lower Silesia",
            state="Downtown",
            city="Wroclaw",
            postal_code="53-310",
            address="Seasame Street",
        )

        prop = Property.objects.create(
            name="Some name",
            rental_type=Property.Rentals.Entire_Home.value,
            property_type=Property.Types.Condo.value,
            organization=organization,
            location=location,
            booking_settings=BookingSettings.objects.create(
                check_in_out=CheckInOut.objects.create(
                    check_in_from="8:10", check_in_to="12:20", check_out_until="10:30"
                )
            ),
            descriptions=ListingDescriptions.objects.create(
                description="Desc", things_to_do="Things to do", summary="Summary"
            ),
        )

        Availability.objects.create(prop=prop)

        contact = Contact.objects.create(
            first_name="Bob",
            last_name="Rob",
            email="email@example.org",
            secondary_email="email2@example.org",
            phone="+1999999997",
            secondary_phone="+1999999996",
            organization=cls.user.organization,
        )
        cls.reservation = Reservation.objects.create(
            start_date=cls.today,
            end_date=cls.today + timedelta(days=2),
            price="100.00",
            paid="0.00",
            prop=prop,
            guest=contact,
        )

    def test_substitute(self):
        m = mappers.Mapper(self.reservation, self.user)

        with self.subTest(msg="Default vars"):
            message = (
                "{{property_address}} {{agent_name}} {{guest_name}} "
                "{{listing_url}} {{reservation_id}} {{reservation_price}} "
                "{{adults}} {{children}} {{guest_count}} "
                "{{num_nights}} {{arrival_date}} {{check_in_from}} "
                "{{check_in_to}} {{check_out_until}} {{things_to_do}} "
                "{{min_stay}} {{max_stay}} {{guest_email}} "
                "{{guest_secondary_email}} {{guest_phone}} {{guest_secondary_phone}} "
                "{{agent_email}} {{agent_phone}} {{cleaner_name}} "
                "{{cleaner_email}} {{cleaner_phone}} {{property_name}} "
                "{{city}} {{country}} {{continent}} "
                "{{region}} {{state}} {{postal_code}} {{property_type}} "
                "{{rental_type}} {{bedrooms}} {{bathrooms}} "
                "{{max_guests}} {{summary}} {{description}} "
            )

            with self.subTest(msg="All Values"):
                formatted_message = m.substitute(message)
                self.assertNotIn("{}", formatted_message, "Variables should be substituted")

            with self.subTest(msg="Min Values"):
                m = mappers.Mapper(
                    Reservation.objects.create(
                        start_date=self.today,
                        end_date=self.today + timedelta(days=2),
                        price="100.00",
                        paid="0.00",
                        prop=Property.objects.create(
                            name="Some name2",
                            rental_type=Property.Rentals.Entire_Home.value,
                            property_type=Property.Types.Condo.value,
                            organization=self.user.organization,
                            location=Location.objects.create(address="Seasame Street"),
                        ),
                        guest=Contact.objects.create(
                            first_name="Bob",
                            last_name="Rob",
                            email="email2@example.org",
                            organization=self.user.organization,
                        ),
                    ),
                    self.user,
                )

                formatted_message = m.substitute(message)
                self.assertNotIn("{{", formatted_message, "Variables should be substituted")

        with self.subTest(msg="With custom vars"):
            message = "{{key}} {{another}}"
            custom_vars = (("key", "value1"), ("another", "value2"))
            formatted_message = m.substitute(message, custom_vars)
            for _, value in custom_vars:
                self.assertIn(value, formatted_message)

        with self.subTest(msg="With None"):
            message = ""
            custom_vars = None
            formatted_message = m.substitute(message, custom_vars)
            self.assertEqual(message, formatted_message)


class TemplateViewSetTestCase(TestCase):
    def test_filter_backends(self):
        self.assertIn(OrganizationFilter, views.TemplateViewSet.filter_backends)


class VariableViewSetTestCase(TestCase):
    def test_filter_backends(self):
        self.assertIn(OrganizationFilter, views.VariableViewSet.filter_backends)
"""

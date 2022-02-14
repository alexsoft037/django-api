from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from psycopg2.extras import DateRange

from accounts.models import Organization
from crm.models import Contact
from listings import models
from listings.calendars.models import ExternalCalendar
from listings.choices import WeekDays
from listings.services import IsPropertyAvailable


class IsPropertyAvailableTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.start = date(2018, 2, 19)
        cls.end = cls.start + timedelta(days=10)

        cls.organization = Organization.objects.create()
        cls.prop = models.Property.objects.create(
            name="Name",
            property_type=models.Property.Types.Apartment.value,
            rental_type=models.Property.Rentals.Private.value,
            status=models.Property.Statuses.Active.value,
            organization=cls.organization,
        )

        models.TurnDay.objects.create(
            prop=cls.prop, time_frame=DateRange(None, None), days=[WeekDays.Monday.value]
        )

        models.Availability.objects.create(
            prop=cls.prop, time_frame=DateRange(None, None), min_stay=9, max_stay=20
        )

        models.Rate.objects.create(
            prop=cls.prop,
            nightly=1,
            time_frame=DateRange(date(2018, 4, 8), date(2018, 4, 11)),
            seasonal=True,
        )

        cls.reservation = models.Reservation.objects.create(
            start_date=cls.start - timedelta(days=10),
            end_date=cls.start - timedelta(days=1),
            price=Decimal("0"),
            paid=Decimal("0.00"),
            guest=Contact.objects.create(organization=cls.organization),
            prop=cls.prop,
        )

        models.Reservation.objects.create(
            start_date=cls.start + timedelta(days=57),
            end_date=cls.start + timedelta(days=60),
            price=Decimal("0"),
            paid=Decimal("0.00"),
            prop=cls.prop,
            guest=Contact.objects.create(organization=cls.organization),
            status=models.Reservation.Statuses.Inquiry_Blocked.value,
        )

        models.Reservation.objects.create(
            start_date=date(2018, 6, 15),
            end_date=date(2018, 6, 25),
            price=Decimal("0"),
            paid=Decimal("0.00"),
            prop=cls.prop,
            expiration=timezone.now(),
            guest=Contact.objects.create(organization=cls.organization),
            status=models.Reservation.Statuses.Inquiry_Blocked.value,
        )

        models.Reservation.objects.create(
            start_date=date(2018, 6, 4),
            end_date=date(2018, 6, 13),
            price=Decimal("0"),
            paid=Decimal("0.00"),
            prop=cls.prop,
            expiration=timezone.now() + timedelta(days=7),
            guest=Contact.objects.create(organization=cls.organization),
            status=models.Reservation.Statuses.Inquiry_Blocked.value,
        )

        cls.blocking = models.Blocking.objects.create(
            time_frame=DateRange(date(2018, 10, 8), date(2018, 10, 11)),
            summary="Some fixes",
            prop=cls.prop,
        )

        models.Blocking.objects.create(
            time_frame=DateRange(date(2018, 10, 13), None), summary="Some fixes", prop=cls.prop
        )

        cozmo_calendar = cls.prop.cozmo_calendar
        ExternalCalendar.objects.create(
            cozmo_cal=cozmo_calendar, name="synced", url="http://example.org/1/", data=raw_ical
        )

    def test_available(self):

        with self.subTest("Property is available"):
            ipa = IsPropertyAvailable(self.prop, self.start, self.end)
            ipa.run_check()

            self.assertTrue(ipa.is_available())
            self.assertEqual([], ipa.conflicts)
            self.assertEqual([], ipa.blocked_days)

        with self.subTest("Property is not active"):
            self.prop.status = self.prop.Statuses.Disabled
            ipa = IsPropertyAvailable(self.prop, self.start, self.end)
            ipa.run_check()

            self.assertFalse(ipa.is_available())
            self.assertIn(IsPropertyAvailable.messages["not_active"], ipa.conflicts)
            self.prop.refresh_from_db()

        with self.subTest("Wrong Turn day"):
            ipa = IsPropertyAvailable(self.prop, self.start + timedelta(days=1), self.end)
            ipa.run_check()

            self.assertFalse(ipa.is_available())
            self.assertIn(IsPropertyAvailable.messages["turn_days"], ipa.conflicts)
            self.assertEqual([], ipa.blocked_days)

        with self.subTest("Minimum day requirements not meet"):

            with self.subTest("Min"):
                ipa = IsPropertyAvailable(self.prop, self.start, self.end - timedelta(days=5))
                ipa.run_check()

                self.assertFalse(ipa.is_available())
                self.assertIn(IsPropertyAvailable.messages["stay"], ipa.conflicts)
                self.assertEqual([], ipa.blocked_days)

            with self.subTest("Max"):
                ipa = IsPropertyAvailable(self.prop, self.start, self.end + timedelta(days=20))
                ipa.run_check()

                self.assertFalse(ipa.is_available())
                self.assertIn(IsPropertyAvailable.messages["stay"], ipa.conflicts)
                self.assertEqual([], ipa.blocked_days)

        with self.subTest("Seasonal Rate: Minimum day requirements not meet"):
            ipa = IsPropertyAvailable(self.prop, date(2018, 4, 8), date(2018, 4, 11))
            ipa.run_check()

            self.assertFalse(ipa.is_available())
            self.assertIn(IsPropertyAvailable.messages["stay"], ipa.conflicts)
            self.assertEqual([], ipa.blocked_days)

        with self.subTest("Clash with other reservation"):
            start = self.start - timedelta(days=14)
            ipa = IsPropertyAvailable(self.prop, start, start + timedelta(days=10))
            ipa.run_check()

            self.assertFalse(ipa.is_available())
            self.assertIn(IsPropertyAvailable.messages["reservation"], ipa.conflicts)
            self.assertEqual(
                [{"end_date": date(2018, 2, 15), "start_date": date(2018, 2, 9)}], ipa.blocked_days
            )

        with self.subTest("Clash with expired blocking inquiry"):
            ipa = IsPropertyAvailable(self.prop, date(2018, 6, 18), date(2018, 6, 30))
            ipa.run_check()
            self.assertTrue(ipa.is_available())

        with self.subTest("Clash with not expired blocking inquiry"):
            ipa = IsPropertyAvailable(self.prop, date(2018, 6, 4), date(2018, 6, 15))
            ipa.run_check()
            self.assertFalse(ipa.is_available())
            self.assertIn(IsPropertyAvailable.messages["reservation"], ipa.conflicts)
            self.assertEqual(
                [{"start_date": date(2018, 6, 4), "end_date": date(2018, 6, 13)}], ipa.blocked_days
            )

        with self.subTest("Clash with blocked inquire"):
            ipa = IsPropertyAvailable(
                self.prop, self.start + timedelta(days=56), self.start + timedelta(days=68)
            )
            ipa.run_check()

            self.assertFalse(ipa.is_available())
            self.assertIn(IsPropertyAvailable.messages["reservation"], ipa.conflicts)
            self.assertEqual(
                [{"end_date": date(2018, 4, 20), "start_date": date(2018, 4, 17)}],
                ipa.blocked_days,
            )

        # with self.subTest("Does not clash with Calendar event"):
        #     start = date(2018, 7, 23)
        #     ipa = IsPropertyAvailable(self.prop, start, start + timedelta(days=10))
        #     ipa.run_check()
        #     self.assertTrue(ipa.is_available())

        with self.subTest("Clash with blocking"):
            ipa = IsPropertyAvailable(
                self.prop,
                self.blocking.time_frame.lower,
                self.blocking.time_frame.lower + timedelta(days=10),
            )
            ipa.run_check()

            self.assertFalse(ipa.is_available())
            self.assertIn(IsPropertyAvailable.messages["blockings"], ipa.conflicts)
            self.assertEqual(
                [
                    {"end_date": date(2018, 10, 11), "start_date": date(2018, 10, 8)},
                    {"end_date": date(2018, 10, 18), "start_date": date(2018, 10, 13)},
                ],
                ipa.blocked_days,
            )


raw_ical = b"""
BEGIN:VCALENDAR
PRODID:-//Google Inc//Google Calendar 70//EN
VERSION:2.0
CALSCALE:GREGORIAN
METHOD:PUBLISH
X-WR-CALNAME:Public Test
X-WR-TIMEZONE:Europe/Warsaw
X-WR-CALDESC:Some desc
BEGIN:VEVENT
DTSTART:20180726T050000Z
DTEND:20180728T060000Z
DTSTAMP:20180727T143046Z
UID:very-unique-id@google.com
CREATED:20170725T112223Z
DESCRIPTION:
LAST-MODIFIED:20180725T113140Z
LOCATION:
SEQUENCE:0
STATUS:CONFIRMED
SUMMARY:Timezone test
TRANSP:OPAQUE
END:VEVENT
BEGIN:VEVENT
DTSTART:20180728T043000Z
DTEND:20180729T053000Z
DTSTAMP:20180727T143046Z
UID:other-unique-id@google.com
CREATED:20170725T112229Z
DESCRIPTION:
LAST-MODIFIED:20180725T112237Z
LOCATION:
SEQUENCE:0
STATUS:CONFIRMED
SUMMARY:Other
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
"""

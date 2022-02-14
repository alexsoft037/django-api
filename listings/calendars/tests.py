import datetime as dt
import logging
from unittest import mock
from urllib.error import URLError
from uuid import uuid4

from celery.exceptions import Ignore
from django.http import Http404
from django.test import TestCase
from django.utils import timezone
from icalendar import Calendar
from rest_framework.exceptions import ValidationError
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST

from cozmo_common.filters import OrganizationFilter
from cozmo_common.functions import datetime_to_date, end_date_plus
from listings import filters
from listings.models import Blocking, Property, Reservation
from . import serializers, tasks
from .models import AbstractExternalCalendar, CheckCalendar, CozmoCalendar, ExternalCalendar
from .views import CalendarViewSet, ExternalCalendarViewSet

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
DTSTART:20170726T050000Z
DTEND:20170726T060000Z
DTSTAMP:20170727T143046Z
UID:very-unique-id@google.com
CREATED:20170725T112223Z
DESCRIPTION:
LAST-MODIFIED:20170725T113140Z
LOCATION:
SEQUENCE:0
STATUS:CONFIRMED
SUMMARY:Timezone test
TRANSP:OPAQUE
END:VEVENT
BEGIN:VEVENT
DTSTART:20170728
DTEND:20170729
DTSTAMP:20170727T143046Z
UID:other-unique-id@google.com
CREATED:20170725T112229Z
DESCRIPTION:
LAST-MODIFIED:20170725T112237Z
LOCATION:
SEQUENCE:0
STATUS:CONFIRMED
SUMMARY:Other
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
"""

diff_raw_ical = b"""
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
DTEND:20180726T060000Z
DTSTAMP:20170727T143046Z
UID:very-unique-id@google.com
CREATED:20170725T112223Z
DESCRIPTION:
LAST-MODIFIED:20170725T113140Z
LOCATION:
SEQUENCE:0
STATUS:CONFIRMED
SUMMARY:Timezone test 2
TRANSP:OPAQUE
END:VEVENT
BEGIN:VEVENT
DTSTART:20170828
DTEND:20170829
DTSTAMP:20170727T143046Z
UID:other-unique-id-diff@google.com
CREATED:20170725T112229Z
DESCRIPTION:
LAST-MODIFIED:20170725T112237Z
LOCATION:
SEQUENCE:0
STATUS:CONFIRMED
SUMMARY:Other
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
"""


# Model tests


class CozmoCalendarTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.prop = Property.objects.create(
            name="Name",
            property_type=Property.Types.Apartment.value,
            rental_type=Property.Rentals.Private.value,
        )

    @classmethod
    def tearDownClass(cls):
        Property.objects.all().delete()
        super().tearDownClass()

    def test_autocreate_calendar_for_property(self):
        self.assertIsInstance(self.prop.cozmo_calendar, CozmoCalendar)

    def test_have_url(self):
        self.assertIsInstance(self.prop.cozmo_calendar.url, str)

    def test_refresh_ical(self):
        cal = self.prop.cozmo_calendar
        ExternalCalendar.objects.create(
            name=f"External calendar", cozmo_cal=cal, data=raw_ical, url="http://example.org"
        )
        today = dt.date.today()
        Blocking.objects.bulk_create(
            Blocking(
                time_frame=(today + dt.timedelta(i * 4), today + dt.timedelta((i + 1) * 4)),
                prop=self.prop,
            )
            for i in range(5)
        )
        Reservation.objects.bulk_create(
            Reservation(
                prop=self.prop,
                start_date=today + dt.timedelta(i * 2),
                end_date=today + dt.timedelta((i + 1) * 2),
                price=10,
                paid=10,
            )
            for i in range(2)
        )
        self.assertEqual(cal.data, None)
        cal.refresh_ical()
        ical = Calendar.from_ical(bytes(cal.data))

        ical_events = sum(len(ex_cal.raw_events) for ex_cal in cal.externalcalendar_set.all())
        blockings = Blocking.objects.filter(prop=self.prop).count()
        reservations = Reservation.objects.filter(prop=self.prop).count()
        self.assertEqual(
            len(ical.walk("VEVENT")),
            ical_events + blockings + reservations,
            "iCal should create events from external cals, blockings and reservations",
        )

        with self.subTest("Merge events"):
            cal.merge_events = True
            cal.refresh_ical()
            ical = Calendar.from_ical(bytes(cal.data))
            self.assertLess(
                len(ical.walk("VEVENT")),
                ical_events + blockings + reservations,
                "iCal should merge overlapping events",
            )

        with self.subTest("Merge events but no events"):
            self.prop.blocking_set.all().delete()
            self.prop.reservation_set.all().delete()
            self.prop.cozmo_calendar.externalcalendar_set.all().delete()
            cal.refresh_ical()
            ical = Calendar.from_ical(bytes(cal.data))
            self.assertEqual(len(ical.walk("VEVENT")), 0)

        with self.subTest("Don't merge events but no events"):
            cal.merge_events = True
            cal.refresh_ical()
            ical = Calendar.from_ical(bytes(cal.data))
            self.assertEqual(len(ical.walk("VEVENT")), 0)


class AbstractExtCalendarTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cal = AbstractExternalCalendar(data=raw_ical, url="http://example.org/ical/")

    def setUp(self):
        self.cal.data = raw_ical

    def test_raw_events(self):
        events = self.cal.raw_events
        self.assertEqual(len(events), 2)
        self.assertEqual(self.cal.events_count, 2)

    # @mock.patch("listings.calendars.models.icalendar.Calendar.from_ical", side_effect=ValueError)
    # def test_raw_events_invalid(self, m_ical):
    #     with self.assertLogs("cozmo", level=logging.WARNING):
    #         events = self.cal.raw_events
    #         self.assertListEqual(events, [])

    def test_events(self):
        events = self.cal.events
        self.assertEqual(len(events), 2)
        event = events[0]
        self.assertIn("start", event)
        self.assertIn("end", event)

    @mock.patch("listings.calendars.models.urlopen", side_effect=URLError("ERROR"))
    def test_fetch_cant_connect(self, m_get):
        with self.assertRaises(ValueError):
            self.cal.fetch()

    @mock.patch("listings.calendars.models.urlopen", return_value=mock.MagicMock())
    def test_fetch_error_resp(self, m_get):
        with self.assertRaises(ValueError):
            self.cal.fetch()

    @mock.patch("listings.calendars.models.urlopen", return_value=mock.MagicMock())
    @mock.patch("listings.calendars.models.icalendar.Calendar.from_ical", side_effect=ValueError)
    def test_fetch_cant_parse(self, m_ical, m_get):
        with self.assertRaises(ValueError):
            self.cal.fetch()

    @mock.patch("listings.calendars.models.AbstractExternalCalendar.save")
    @mock.patch("listings.calendars.models.urlopen", return_value=mock.MagicMock())
    @mock.patch("listings.calendars.models.icalendar.Calendar.from_ical")
    def test_fetch_commit(self, m_ical, m_get, m_save):
        self.cal.fetch(commit=True)
        m_save.assert_called_once()

        m_save.reset_mock()
        self.cal.fetch()
        m_save.assert_not_called()

        m_save.reset_mock()
        self.cal.fetch(commit=False)
        m_save.assert_not_called()


class CheckCalendarTestCase(TestCase):
    @mock.patch("listings.calendars.models.CheckCalendar.raw_events")
    @mock.patch("listings.calendars.models.CheckCalendar._parse_events")
    def test_filter_events(self, m_parse, m_raw_events):
        now = timezone.now()
        too_old = {"start": now - dt.timedelta(days=91)}
        too_new = {"start": now + dt.timedelta(days=365, seconds=10)}
        okay = [
            {"start": now, "end": now + dt.timedelta(days=365)},
            {"start": now - dt.timedelta(days=89)},
            {"start": now + dt.timedelta(days=364)},
        ]
        all_events = too_old, too_new, *okay
        m_parse.side_effect = all_events

        cal = CheckCalendar()
        cal.raw_events = all_events
        filtered_events = cal.events
        self.assertEqual(m_parse.call_count, len(all_events))
        self.assertListEqual(filtered_events, okay)

    @mock.patch("listings.calendars.models.CheckCalendar.raw_events")
    @mock.patch("listings.calendars.models.CheckCalendar._parse_events")
    def test_filter_events_with_dates(self, m_parse, m_raw_events):
        now = timezone.now().date()
        too_old = {"start": now - dt.timedelta(days=90)}
        too_new = {"start": now + dt.timedelta(days=365, seconds=10)}
        okay = [
            {"start": now, "end": now + dt.timedelta(days=365)},
            {"start": now - dt.timedelta(days=89)},
            {"start": now + dt.timedelta(days=364)},
        ]
        all_events = too_old, too_new, *okay
        m_parse.side_effect = all_events

        cal = CheckCalendar()
        cal.raw_events = all_events
        filtered_events = cal.events
        self.assertEqual(m_parse.call_count, len(all_events))
        self.assertListEqual(filtered_events, okay)


# Serializers tests


class CheckCalendarSerializerTestCase(TestCase):
    def setUp(self):
        self.ser = serializers.CheckCalendarSerializer()
        self.url = "http://example.org/ical/"

    @mock.patch(
        "listings.calendars.serializers.models.CheckCalendar.fetch", side_effect=ValueError
    )
    def test_invalid_ical(self, m_fetch):
        with self.assertRaises(ValidationError):
            self.ser.validate_url(self.url)

    @mock.patch(
        "listings.calendars.serializers.models.CheckCalendar.fetch", side_effect=ValueError
    )
    def test_cant_connect(self, m_fetch):
        with self.assertRaises(ValidationError):
            self.ser.validate_url(self.url)

    @mock.patch("listings.calendars.serializers.models.CheckCalendar.fetch", return_value=True)
    def test_can_check_many_times(self, m_fetch):
        context = {"request": mock.MagicMock(**{"user.organization": None})}

        first = serializers.CheckCalendarSerializer(data={"url": self.url}, context=context)
        self.assertTrue(first.is_valid())

        second = serializers.CheckCalendarSerializer(data={"url": self.url}, context=context)
        self.assertTrue(second.is_valid())


class ExternalCalendarSerializerTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.prop = Property.objects.create(
            name="Name",
            property_type=Property.Types.Apartment.value,
            rental_type=Property.Rentals.Private.value,
        )

    @mock.patch("listings.calendars.models.urlopen", return_value=mock.MagicMock())
    @mock.patch("listings.calendars.models.icalendar.Calendar.from_ical")
    def test_fetch_calendar_on_url_update(self, m_ical, m_get):
        old_data = b"Old data"
        new_data = b"New data"
        m_get.return_value.read.return_value = new_data

        cal = ExternalCalendar.objects.create(
            name="Some name",
            url="http://example.org/old/",
            data=old_data,
            cozmo_cal=self.prop.cozmo_calendar,
        )
        ser = serializers.ExternalCalendarSerializer(
            cal, data={"url": "http://example.org/new/"}, partial=True
        )

        self.assertTrue(ser.is_valid())
        updated_cal = ser.save()
        self.assertEqual(updated_cal.data, new_data)

        with self.subTest("Should not fetch when url stays the same"):
            m_ical.reset_mock()
            m_get.reset_mock()
            serializer = serializers.ExternalCalendarSerializer(
                cal, data={"name": "Updated name"}, partial=True
            )
            self.assertTrue(serializer.is_valid())
            m_get.assert_not_called()
            m_ical.assert_not_called()

    @mock.patch("listings.calendars.serializers.ExternalCalendarSerializer.validate_url")
    def test_empty_description(self, m_url):
        ser = serializers.ExternalCalendarSerializer(
            data={
                "url": "http://example.org/",
                "name": "Unique name",
                "description": "",
                "cozmo_cal": self.prop.cozmo_calendar.pk,
            }
        )
        self.assertTrue(ser.is_valid(), ser.errors)

    @mock.patch(
        "listings.calendars.serializers.ExternalCalendarSerializer.validate_url",
        side_effect=lambda url: url,
    )
    def test_create_saves_correctly(self, m_url):
        serializer = serializers.ExternalCalendarSerializer(
            data={"url": "http://example.org/", "name": "Unique name"},
            context={"cozmo_cal_id": self.prop.cozmo_calendar.pk},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer._cal = mock.MagicMock(data=None)
        self.assertIsInstance(serializer.save(), ExternalCalendar)


# Tasks tests


class FetchCalendarTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.prop = Property.objects.create(
            name="Name",
            property_type=Property.Types.Apartment.value,
            rental_type=Property.Rentals.Private.value,
        )
        cls.e_cal = ExternalCalendar.objects.create(cozmo_cal=cls.prop.cozmo_calendar)

    @classmethod
    def tearDownClass(cls):
        cls.prop.delete()
        super().tearDownClass()

    def setUp(self):
        self.orig_date = dt.datetime.fromtimestamp(
            self.e_cal.date_updated.timestamp(), self.e_cal.date_updated.tzinfo
        )

    def test_does_not_exist(self):
        non_existings_id = uuid4()
        self.assertEqual(CozmoCalendar.objects.filter(id=non_existings_id).count(), 0)

        with self.assertRaises(Ignore) as e:
            tasks.fetch_calendar(non_existings_id)
            self.assertIn(str(non_existings_id), e.msg)

    @mock.patch("listings.calendars.tasks.ExternalCalendar.fetch", side_effect=ValueError)
    def test_cant_connect(self, m_fetch):
        with self.assertLogs(level=logging.WARNING):
            tasks.fetch_calendar(self.e_cal.pk)
        self.was_date_updated()

    @mock.patch("listings.calendars.tasks.ExternalCalendar.fetch", side_effect=ValueError)
    def test_cant_parse(self, m_fetch):
        with self.assertLogs(level=logging.WARNING):
            tasks.fetch_calendar(self.e_cal.pk)
        self.was_date_updated()

    @mock.patch("listings.calendars.tasks.ExternalCalendar.fetch")
    def test_ok(self, m_fetch):
        tasks.fetch_calendar(self.e_cal.pk)
        self.was_date_updated()

    def was_date_updated(self):
        self.e_cal.refresh_from_db()
        self.assertLess(self.orig_date, self.e_cal.date_updated)


class FetchCalendarsTestCase(TestCase):
    def test_periodic_task(self):
        every_seconds = 15 * 60
        self.assertEqual(tasks.fetch_calendars.run_every.seconds, every_seconds)

    @mock.patch("listings.calendars.tasks.group")
    def test_sync_only_old(self, m_group):
        prop = Property.objects.create(
            name="Name",
            property_type=Property.Types.Apartment.value,
            rental_type=Property.Rentals.Private.value,
        )
        synced = ExternalCalendar.objects.create(
            cozmo_cal=prop.cozmo_calendar, name="synced", url="http://example.org/1/"
        )
        not_synced = ExternalCalendar.objects.create(
            cozmo_cal=prop.cozmo_calendar, name="not synced", url="http://example.org/2/"
        )
        old_date = timezone.now() - tasks.UPDATE_EACH
        ExternalCalendar.objects.filter(pk=not_synced.pk).update(date_updated=old_date)

        tasks.fetch_calendars.apply()
        args, kwargs = m_group.call_args
        synced_calls = tuple(args[0])
        self.assertDictEqual(kwargs, {})
        self.assertEqual(len(synced_calls), 1)

        updated_date = synced.date_updated
        synced.refresh_from_db()
        self.assertEqual(updated_date, synced.date_updated)

        not_synced.refresh_from_db()
        self.assertEqual(old_date, not_synced.date_updated)

        prop.delete()


# Views tests


class CalendarViewSetTestCase(TestCase):

    ViewClass = CalendarViewSet

    def test_filter_by_prop(self):
        self.assertIn(filters.PropertyIdFilter, self.ViewClass.filter_backends)
        self.assertIn(OrganizationFilter, self.ViewClass.filter_backends)

    def test_filename(self):
        prop = Property.objects.create()
        request = mock.Mock(query_params={})
        view = self.ViewClass(request=request)

        with mock.patch.object(view, "get_object", return_value=prop.cozmo_calendar):

            with self.subTest("Correct request & response"):
                resp = view.ical(request, prop.cozmo_calendar.id)
                self.assertIn(f"filename=cozmo-{prop.id}.ics", resp["Content-Disposition"])

            with self.subTest("Non existing external calendar"):
                invalid_ext_cal_id = 123
                request.query_params["_target"] = invalid_ext_cal_id
                self.assertFalse(
                    prop.cozmo_calendar.externalcalendar_set.filter(id=invalid_ext_cal_id).exists()
                )
                # with self.assertRaises(Http404):
                #     view.ical(request, prop.cozmo_calendar.id)

            with self.subTest("Existing external calendar"):
                ext_cal = ExternalCalendar.objects.create(
                    data=b"BEGIN:VCALENDAR\nEND:VCALENDAR", cozmo_cal=prop.cozmo_calendar
                )
                request.query_params["_target"] = ext_cal.id
                resp = view.ical(request, prop.cozmo_calendar.id)
                self.assertIn(
                    f"filename=cozmo-{prop.id}-{ext_cal.id}.ics", resp["Content-Disposition"]
                )


class ExternalCalendarViewSetTestCase(TestCase):
    def test_fetch(self):
        prop = Property.objects.create(
            name="Name",
            property_type=Property.Types.Apartment.value,
            rental_type=Property.Rentals.Private.value,
        )
        external_calendar = ExternalCalendar.objects.create(
            cozmo_cal=prop.cozmo_calendar, name="synced", url="http://example.org/1/"
        )

        request = mock.MagicMock(data={})
        view = ExternalCalendarViewSet(action="post", request=request)
        view.kwargs = dict(cozmo_cal_id=str(prop.cozmo_calendar.id), pk=external_calendar.id)
        view.format_kwarg = None

        with mock.patch(
            "listings.calendars.models.urlopen",
            return_value=mock.MagicMock(read=mock.MagicMock(return_value=raw_ical)),
        ):

            with mock.patch(
                "listings.calendars.models.icalendar.Calendar.from_ical", side_effect=ValueError
            ):
                with self.subTest(msg="Parse problem"):
                    resp = view.fetch(request)
                    self.assertEqual(resp.status_code, HTTP_400_BAD_REQUEST)

            with mock.patch(
                "listings.calendars.models.icalendar.Calendar.from_ical", return_value=Calendar()
            ):

                with self.subTest(msg="Calendar exists"):
                    resp = view.fetch(request)
                    self.assertEqual(resp.status_code, HTTP_200_OK)

        with self.subTest(msg="Fetch problem"):
            resp = view.fetch(request)
            self.assertEqual(resp.status_code, HTTP_400_BAD_REQUEST)

        with self.subTest(msg="Calendar not found"):
            with self.assertRaises(Http404):
                view.kwargs = dict(cozmo_cal_id=str(prop.cozmo_calendar.id), pk=None)
                resp = view.fetch(request)


class ExternalCalendarModelTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        prop = Property.objects.create(
            name="Name",
            property_type=Property.Types.Apartment.value,
            rental_type=Property.Rentals.Private.value,
        )
        cozmo_cal = prop.cozmo_calendar
        cls.external_cal = ExternalCalendar.objects.create(
            name=f"External calendar", cozmo_cal=cozmo_cal, data=raw_ical, url="http://example.org"
        )

    def _assert_events(self, cal_events):
        for event in cal_events:
            event_uid = event.get("UID")
            cozmo_event = self.external_cal.event_set.get(uid=event_uid)
            start_date = datetime_to_date(event.get("DTSTART").dt)
            end_date = end_date_plus(start_date, datetime_to_date(event.get("DTEND").dt))
            self.assertIsNotNone(cozmo_event)
            self.assertEqual(start_date, cozmo_event.start_date)
            self.assertEqual(end_date, cozmo_event.end_date)
            self.assertEqual(event.get("DTSTAMP").dt, cozmo_event.stamp)
            self.assertTrue(str(event.get("SUMMARY")) in cozmo_event.summary)

    def test_populate_events(self):
        self.assertEqual(self.external_cal.event_set.count(), 2)
        ical = Calendar.from_ical(raw_ical)
        events = ical.walk(name="VEVENT")
        self._assert_events(events)

        # Modify existing external calendar
        self.external_cal.data = diff_raw_ical
        self.external_cal.save()
        self.assertEqual(self.external_cal.event_set.count(), 2)
        new_ical = Calendar.from_ical(diff_raw_ical)
        new_events = new_ical.walk(name="VEVENT")
        self._assert_events(new_events)

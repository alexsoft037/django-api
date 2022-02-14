import datetime as dt
import hashlib
import logging
import uuid
from hashlib import md5
from itertools import chain
from operator import attrgetter, methodcaller
from urllib.error import URLError
from urllib.request import urlopen, Request

import icalendar
from django.conf import settings
from django.contrib.postgres.indexes import BrinIndex
from django.db import models
from django.utils import timezone
from psycopg2._range import DateRange

from cozmo_common.functions import datetime_to_date, end_date_plus
from cozmo_common.utils import get_ical_friendly_date
from listings.choices import ReservationStatuses

logger = logging.getLogger(__name__)


def daterange_to_event(drange: DateRange):
    return icalendar.Event(
        {
            "SUMMARY": "Cozmo Event",
            "DTSTART;VALUE=DATE": get_ical_friendly_date(drange.lower),
            "DTEND;VALUE=DATE": get_ical_friendly_date(drange.upper),
            "DTSTAMP;VALUE=DATE-TIME": timezone.now().isoformat(),
            "UID": "{}@voyajoy.com".format(
                md5(f"{drange.lower}:{drange.upper}".encode()).hexdigest()  # nosec
            ),
        }
    )


class CozmoCalendar(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merge_events = models.BooleanField(default=False, blank=True)
    data = models.BinaryField(null=True, blank=True)
    date_updated = models.DateTimeField(auto_now=True, blank=True)
    prop = models.OneToOneField(
        "listings.property", on_delete=models.CASCADE, related_name="cozmo_calendar"
    )

    REFRESH_EACH = dt.timedelta(hours=3)

    @property
    def url(self):
        return settings.COZMO_CALENDAR_URL.format(id=self.id)

    def to_ical(self) -> bytes:
        if self.data is None or self.date_updated < (timezone.now() - self.REFRESH_EACH):
            self.refresh_ical()

        return bytes(self.data)

    def _generate_ical(self, excludes=()):
        name = f"{self.prop_id}:Reservations Calendar"
        cal = icalendar.Calendar(
            {
                "VERSION": "2.0",
                "PRODID": "-//Voyajoy Inc//Reservation Calendar 0.2.2//",
                "NAME": name,
                "X-WR-CALNAME": name,
                "CALSCALE": "GREGORIAN",
            }
        )
        external_events = (event for event in self._get_external_events(excludes=excludes))
        reservations = (
            res
            for res in self.prop.reservation_set.all()
            .exclude(
                status__in=[
                    ReservationStatuses.Cancelled,
                    ReservationStatuses.Declined,
                    ReservationStatuses.Inquiry,
                ]
            )
            .iterator()
        )
        blockings = (block for block in self.prop.blocking_set.all().iterator())

        if self.merge_events is False:
            cal.subcomponents.extend(
                map(methodcaller("to_ical"), chain(external_events, reservations, blockings))
            )
        else:
            events = sorted(
                chain(
                    (DateRange(e.start_date, e.end_date) for e in external_events),
                    (DateRange(r.start_date, r.end_date) for r in reservations),
                    (b.time_frame for b in reservations),
                ),
                key=attrgetter("lower"),
            )

            if events:
                merged = [events.pop(0)]
            else:
                merged = []
            for current in events:
                previous = merged[-1]
                if current.lower <= previous.upper:
                    previous._upper = max(previous.upper, current.upper)
                else:
                    merged.append(current)

            cal.subcomponents.extend(map(daterange_to_event, merged))

        return cal.to_ical()

    def to_filtered_ical(self, calendar_id):
        return self._generate_ical(excludes=[calendar_id])

    def refresh_ical(self, commit=True):

        cal = self._generate_ical()
        self.data = cal

        if commit:
            self.save()

    def get_events(self, start_date, end_date):
        return (ev.to_event() for ev in self._get_external_events(start_date, end_date))

    def _get_external_events(self, start_date=None, end_date=None, excludes=()):
        events_queryset = []

        for external in self.externalcalendar_set.exclude(pk__in=excludes):
            queryset = external.event_set.all()
            if start_date or end_date:
                queryset = queryset.filter(
                    start_date__contained_by=DateRange(None, end_date),
                    end_date__contained_by=DateRange(start_date, None, "[]"),
                )
            events_queryset += queryset.iterator()
        return events_queryset


class AbstractExternalCalendar(models.Model):

    url = models.URLField(max_length=500)
    data = models.BinaryField(null=True, blank=True)

    class Meta:
        abstract = True

    @property
    def raw_events(self):
        if self.data is None:
            return []
        try:
            cal = icalendar.Calendar.from_ical(bytes(self.data))
            events = cal.walk(name="VEVENT")
        except ValueError:
            logger.warning("Could not parse calendar %s", self)
            events = []
        return events

    @property
    def events(self):
        return [self._parse_events(ev) for ev in self.raw_events]

    @property
    def events_count(self):
        return len(self.raw_events)

    def fetch(self, commit=False):
        try:
            request = Request(self.url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urlopen(request, timeout=5)
            content = resp.read()
            icalendar.Calendar.from_ical(content)
        except URLError as e:
            logger.info("Could not connect to %s. Reason: %s", self.url, e.args)
            raise ValueError("Could not retrieve calendar")
        except ValueError:
            logger.info("Could not parse calendar %s", self)
            raise ValueError("Could not parse calendar")
        else:
            self.data = content

        if commit:
            self.save()

    def _parse_events(self, ev):
        return {"start": ev["DTSTART"].dt, "end": ev["DTEND"].dt}

    def __str__(self):
        pk = getattr(self, "pk", None)
        return "<Calendar pk={} url={}>".format(pk, self.url)


class CheckCalendar(AbstractExternalCalendar):
    @property
    def events(self):
        today = dt.datetime.combine(timezone.now(), dt.time.min, timezone.get_current_timezone())
        from_date = today - dt.timedelta(days=90)  # around 3 months
        to_date = today + dt.timedelta(days=365)  # around 1 year

        def events_in_period():
            for r_ev in self.raw_events:
                ev = self._parse_events(r_ev)
                ev_start = self._parse_start_date(ev["start"])
                if from_date < ev_start < to_date:
                    yield ev

        return list(events_in_period())

    def _parse_start_date(self, date) -> dt.datetime:
        if not isinstance(date, dt.datetime):
            return dt.datetime.combine(date, dt.time.min, timezone.get_current_timezone())
        if not date.tzinfo or date.tzinfo.utcoffset(date):
            return date.astimezone(timezone.get_current_timezone())
        return date


class ExternalCalendar(AbstractExternalCalendar):
    name = models.CharField(max_length=32)
    date_updated = models.DateTimeField(auto_now=True)
    date_added = models.DateTimeField(auto_now_add=True)
    description = models.TextField(max_length=500, default="", blank=True)
    cozmo_cal = models.ForeignKey("CozmoCalendar", on_delete=models.CASCADE)
    enabled = models.BooleanField(default=True)
    color = models.ForeignKey("CalendarColor", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        unique_together = ("name", "cozmo_cal")

    def populate_events(self):
        cozmo_events = {item["uid"]: item["hash"] for item in self.event_set.values("uid", "hash")}

        def _stamp(stamp):
            if stamp:
                return stamp.dt
            return self.date_updated

        def _recurrence_id(rec_id):
            return rec_id.dt.isoformat() if rec_id else None

        new_events = []
        for event in self.raw_events:
            event_uid = event.get("UID")
            recurrence_id = _recurrence_id(event.get("RECURRENCE-ID"))
            if recurrence_id:
                event_uid = f"{event_uid}:{recurrence_id}"
            event_hash = hashlib.md5(event.to_ical()).hexdigest()  # nosec
            start_date = datetime_to_date(event.get("DTSTART").dt)
            end_date = end_date_plus(start_date, datetime_to_date(event.get("DTEND").dt))
            stamp = _stamp(event.get("DTSTAMP"))
            if event_uid in cozmo_events.keys():
                cozmo_event_hash = cozmo_events.pop(event_uid)
                if event_hash != cozmo_event_hash:
                    ExternalCalendarEvent.objects.filter(external_cal=self, uid=event_uid).update(
                        summary=event.get("SUMMARY"),
                        start_date=start_date,
                        end_date=end_date,
                        stamp=stamp,
                        hash=event_hash,
                    )
            else:
                new_events.append(
                    ExternalCalendarEvent(
                        uid=event_uid,
                        summary=event.get("SUMMARY"),
                        start_date=start_date,
                        end_date=end_date,
                        stamp=stamp,
                        hash=event_hash,
                        external_cal=self,
                    )
                )
        # Remove events that are no longer present
        if cozmo_events:
            ExternalCalendarEvent.objects.filter(uid__in=cozmo_events.keys()).delete()
        if new_events:
            ExternalCalendarEvent.objects.bulk_create(new_events)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        super().save(force_insert, force_update, using, update_fields)
        self.populate_events()


class SyncLog(models.Model):

    date_added = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField()
    events = models.PositiveIntegerField()
    calendar = models.ForeignKey("ExternalCalendar", on_delete=models.CASCADE, related_name="logs")


class CalendarColor(models.Model):
    name = models.CharField(max_length=32, unique=True)
    hex_color = models.CharField(max_length=7)
    date_updated = models.DateTimeField(auto_now=True, null=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)


class ExternalCalendarEvent(models.Model):

    external_cal = models.ForeignKey(
        "ExternalCalendar", on_delete=models.CASCADE, related_name="event_set"
    )
    uid = models.CharField(max_length=255)
    summary = models.CharField(max_length=300, default="")
    start_date = models.DateField()
    end_date = models.DateField()
    stamp = models.DateTimeField(null=True, blank=True)
    hash = models.CharField(max_length=32)
    open = models.BooleanField(default=False)

    date_updated = models.DateTimeField(auto_now=True, null=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        unique_together = ("uid", "external_cal")
        indexes = [BrinIndex(fields=["uid"])]

    @property
    def calendar(self):
        self._cal = self._cal if hasattr(self, "_cal") else self.external_cal
        return self._cal

    @property
    def event_name(self):
        ex_cal_name = self.calendar.name
        summary = f"iCal - {ex_cal_name}"
        if self.summary:
            summary = f"{summary} - {self.summary}"
        return summary

    @property
    def color(self):
        if self.calendar.color:
            return self.calendar.color.hex_color
        return ""

    def to_event(self):
        return {
            "name": self.event_name,
            "color": self.color,
            "open": self.open,
            "id": self.id,
            "time_frame": {"lower": self.start_date, "upper": self.end_date},
        }

    def to_ical(self):
        prop_id = self.calendar.cozmo_cal.prop.id

        return icalendar.Event(
            {
                "SUMMARY": self.event_name,
                "DTSTART;VALUE=DATE": get_ical_friendly_date(self.start_date),
                "DTEND;VALUE=DATE": get_ical_friendly_date(self.end_date),
                "DTSTAMP;VALUE=DATE-TIME": (self.stamp or self.date_updated).isoformat(),
                "UID": "{}@voyajoy.com".format(
                    md5(
                        ":".join(
                            [self.start_date.isoformat(), self.end_date.isoformat(), str(prop_id)]
                        ).encode()
                    ).hexdigest()  # nosec
                ),
            }
        )

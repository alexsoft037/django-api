import datetime as dt

from django.db.models import Q
from psycopg2.extras import DateRange

from listings.calendars.models import ExternalCalendarEvent
from .models import AvailabilitySettings, Reservation


def _date_range(start, end):
    for i in range((end - start).days + 1):
        yield start + dt.timedelta(i)


class IsPropertyAvailable:
    """
    Class provide one public method `is_available` which returns
    message when the given period is blocked or empty string if not.
    """

    messages = {
        "not_active": "Property is not currently available for booking.",
        "advance_bookable": "Reservation date is too distant.",
        "turn_days": "Turn days requirements is not met.",
        "stay": "Minimum night requirement is not met",
        "reservation": "Reservation is unavailable for the specified period.",
        "calendar_events": "Reservation is unavailable for the specified period.",
        "blockings": "Reservation is unavailable for the specified period.",
        "ical_blockings": "Reservation is unavailable for the specified period.",
    }

    def __init__(self, prop, start_date, end_date, **kwargs):

        if kwargs.get("should_sync", False):
            prop.sync()

        self._reservations_excluded = kwargs.get("reservations_excluded", [])

        self.prop = prop
        self.start_date = start_date
        self.end_date = end_date
        self._latest = []

    def _check_prop_state(self):
        return self.prop.status == self.prop.Statuses.Active

    def _check_advance_bookable(self):
        try:
            advance_bookable = self.prop.booking_settings.months_advanced_bookable
        except AttributeError:
            advance_bookable = 0
        today = dt.date.today()
        bookable_to = today + dt.timedelta(days=advance_bookable * 30)
        return not bool(advance_bookable and self.end_date > bookable_to)

    def _check_turn_days(self):
        turn_days_queryset = self.prop.turnday_set
        turn_days = (
            turn_days_queryset.filter(
                time_frame__overlap=DateRange(self.start_date, self.end_date)
            )
            .exclude(time_frame=(None, None))
            .order_by("-time_frame")
        )

        if not turn_days:
            turn_days = turn_days_queryset.filter(time_frame=(None, None))

        if turn_days:
            return self.start_date.weekday() in turn_days.last().days
        return True

    def _check_stay_requirements(self):
        availability_queryset = self.prop.availability_set
        availabilities = (
            availability_queryset.filter(
                time_frame__overlap=DateRange(self.start_date, self.end_date)
            )
            .exclude(time_frame=(None, None))
            .order_by("-time_frame")
        )

        if not availabilities:
            availabilities = availability_queryset.filter(time_frame=(None, None))
        if not availabilities:
            availabilities = AvailabilitySettings.objects.filter(prop=self.prop)

        if availabilities:
            stay_days = (self.end_date - self.start_date).days
            availability = availabilities.last()
            ok = availability.min_stay <= stay_days
            if availability.max_stay:
                ok = ok and stay_days <= availability.max_stay
            return ok
        return True

    def _verify_blocked_days(self, start_date, end_date):
        self._blocked_days.update(
            {day: True for day in _date_range(start_date, end_date) if day in self._blocked_days}
        )

    def _add_latest(self, queryset):
        if queryset:
            latest = queryset.values_list("date_updated", flat=True).latest("date_updated")
            self._latest.append(latest)

    def _check_reservations(self):
        reservations_q = (
            self.prop.reservation_set.exclude(
                status__in=(
                    Reservation.Statuses.Declined.value,
                    Reservation.Statuses.Inquiry.value,
                )
            )
            .exclude(pk__in=[r.pk for r in self._reservations_excluded])
            .filter(
                Q(
                    status__in=(
                        Reservation.Statuses.Accepted.value,
                        Reservation.Statuses.Inquiry_Blocked.value,
                    )
                )
                | Q(
                    status=Reservation.Statuses.Cancelled.value, rebook_allowed_if_cancelled=False
                ),
                start_date__contained_by=DateRange(upper=self.end_date),
                end_date__contained_by=DateRange(lower=self.start_date, bounds="()"),
            )
        )

        self._add_latest(reservations_q)
        expired_inquiries = []
        for reservation in reservations_q:
            if reservation.is_inquiry_expired:
                expired_inquiries.append(reservation)
                continue
            self._verify_blocked_days(reservation.start_date, reservation.end_date)

        has_blocking_reservations = len(reservations_q) == len(expired_inquiries)
        return has_blocking_reservations

    def _check_blockings(self):
        blockings = self.prop.blocking_set.filter(
            time_frame__overlap=(self.start_date, self.end_date)
        )

        self._add_latest(blockings)

        for blocking in blockings:
            start = blocking.time_frame.lower or self.start_date
            end = blocking.time_frame.upper or self.end_date
            self._verify_blocked_days(start, end)

        return not blockings

    def _check_ical_blockings(self):
        external_calendar_set = self.prop.cozmo_calendar.externalcalendar_set.values_list("pk")
        external_blocking_dates = ExternalCalendarEvent.objects.filter(
            external_cal__in=external_calendar_set,
            start_date__contained_by=DateRange(upper=self.end_date),
            end_date__contained_by=DateRange(lower=self.start_date, bounds="()"),
        )

        self._add_latest(external_blocking_dates)
        return not external_blocking_dates

    @property
    def latest(self):
        if not hasattr(self, "_conflicts"):
            msg = "You must call `.run_check()` before accessing `.latest`."
            raise AssertionError(msg)
        return max(self._latest or [0])

    @property
    def conflicts(self):
        if not hasattr(self, "_conflicts"):
            msg = "You must call `.run_check()` before accessing `.conflicts`."
            raise AssertionError(msg)
        return self._conflicts

    @property
    def blocked_days(self):
        if not hasattr(self, "_blocked_days"):
            msg = "You must call `.run_check()` before accessing `.blocked_days`."
            raise AssertionError(msg)

        start_date = None
        blockings = {}
        for date, val in self._blocked_days.items():
            if val:
                if not start_date:
                    start_date = date
                blockings[start_date] = date
            else:
                start_date = None

        return [{"start_date": start, "end_date": end} for start, end in blockings.items()]

    def run_check(self):
        self._conflicts = []
        self._blocked_days = {day: False for day in _date_range(self.start_date, self.end_date)}

        if not self._check_prop_state():
            self._conflicts.append(self.messages["not_active"])
        if not self._check_advance_bookable():
            self._conflicts.append(self.messages["advance_bookable"])
        if not self._check_turn_days():
            self._conflicts.append(self.messages["turn_days"])
        if not self._check_stay_requirements():
            self._conflicts.append(self.messages["stay"])
        if not self._check_reservations():
            self._conflicts.append(self.messages["reservation"])
        if not self._check_blockings():
            self._conflicts.append(self.messages["blockings"])
        if not self._check_ical_blockings():
            self._conflicts.append(self.messages["ical_blockings"])

    def is_available(self):
        return not bool(self._conflicts)

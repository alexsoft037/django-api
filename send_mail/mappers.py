import re

from django.contrib.auth import get_user_model
from django.utils.functional import cached_property

from listings.models import Property, Room

User = get_user_model()


class Mapper:
    # Categories
    RESERVATIONS = "reservations"
    USER = "user"
    PROPERTY = "property"
    LISTING = "listing"
    # Sub categories
    GUEST = "guest"
    AGENT = "agent"
    CLEANER = "cleaner"

    variables = [
        dict(name="reservation_id", category=RESERVATIONS),
        dict(name="reservation_price", category=RESERVATIONS),
        dict(name="adults", category=RESERVATIONS),
        dict(name="children", category=RESERVATIONS),
        dict(name="guest_count", category=RESERVATIONS),
        dict(name="num_nights", category=RESERVATIONS),
        dict(name="arrival_date", category=RESERVATIONS),
        dict(name="guest_name", category=USER, sub_category=GUEST),
        dict(name="guest_email", category=USER, sub_category=GUEST),
        dict(name="guest_secondary_email", category=USER, sub_category=GUEST),
        dict(name="guest_phone", category=USER, sub_category=GUEST),
        dict(name="guest_secondary_phone", category=USER, sub_category=GUEST),
        dict(name="agent_name", category=USER, sub_category=AGENT),
        dict(name="agent_email", category=USER, sub_category=AGENT),
        dict(name="agent_phone", category=USER, sub_category=AGENT),
        dict(name="cleaner_name", category=USER, sub_category=CLEANER),
        dict(name="cleaner_email", category=USER, sub_category=CLEANER),
        dict(name="cleaner_phone", category=USER, sub_category=CLEANER),
        dict(name="property_address", category=PROPERTY),
        dict(name="property_name", category=PROPERTY),
        dict(name="city", category=PROPERTY),
        dict(name="country", category=PROPERTY),
        dict(name="continent", category=PROPERTY),
        dict(name="region", category=PROPERTY),
        dict(name="state", category=PROPERTY),
        dict(name="postal_code", category=PROPERTY),
        dict(name="property_type", category=PROPERTY),
        dict(name="rental_type", category=PROPERTY),
        dict(name="bedrooms", category=PROPERTY),
        dict(name="bathrooms", category=PROPERTY),
        dict(name="max_guests", category=PROPERTY),
        dict(name="summary", category=PROPERTY),
        dict(name="description", category=PROPERTY),
        dict(name="listing_url", category=LISTING),
        dict(name="check_in_from", category=LISTING),
        dict(name="check_in_to", category=LISTING),
        dict(name="check_out_until", category=LISTING),
        dict(name="things_to_do", category=LISTING),
        dict(name="min_stay", category=LISTING),
        dict(name="max_stay", category=LISTING),
    ]

    def __init__(self, reservation, user):
        self._reservation = reservation
        self._user = user

    def substitute(self, message, custom_vars=None):
        if custom_vars is None:
            custom_vars = tuple()

        for v in self.variables:
            re_key = r"\{{{key}}}".format(key=v["name"])
            if re.search(re_key, message):
                message = re.sub(re_key, str(getattr(self, v["name"])), message)

        for key, value in custom_vars:
            re_key = r"\{{{key}}}".format(key=key)
            message = re.sub(re_key, value, message)

        return message

    @property
    def property_address(self):
        return self._reservation.prop.full_address

    @property
    def agent_name(self):
        return self._user.first_name

    @property
    def guest_name(self):
        name = " ".join(
            (self._reservation.guest.first_name, self._reservation.guest.last_name)
        ).strip()
        if name:
            return name
        return ""

    @property
    def listing_url(self):
        return "http://example.org/listing/"  # FIXME

    @property
    def reservation_id(self):
        return self._reservation.id

    @property
    def reservation_price(self):
        return self._reservation.price

    @property
    def children(self):
        return self._reservation.guests_children

    @property
    def adults(self):
        return self._reservation.guests_adults

    @property
    def guest_count(self):
        return self._reservation.guests_adults \
               + self._reservation.guests_children + self._reservation.guests_infants

    @property
    def num_nights(self):
        return (self._reservation.end_date - self._reservation.start_date).days

    @property
    def arrival_date(self):
        return self._reservation.start_date

    @property
    def departure_date(self):
        return self._reservation.end_date

    @property
    def check_in_from(self):
        try:
            value = self._reservation.prop.booking_settings.check_in_out.check_in_from
        except AttributeError:
            value = ""
        return value

    @property
    def check_in_to(self):
        try:
            value = self._reservation.prop.booking_settings.check_in_out.check_in_to
        except AttributeError:
            value = ""
        return value

    @property
    def check_out_until(self):
        try:
            value = self._reservation.prop.booking_settings.check_in_out.check_out_until
        except AttributeError:
            value = ""
        return value

    @property
    def things_to_do(self):
        try:
            value = self._reservation.prop.descriptions.things_to_do
        except AttributeError:
            value = ""
        return value

    @property
    def min_stay(self):
        qs = self._reservation.prop.availability_set.filter(
            time_frame__overlap=(self._reservation.start_date, self._reservation.end_date)
        )
        if qs.count() == 1:
            return qs.get().min_stay
        if qs.count() > 1:
            qs.exclude(time_frame=(None, None))
            return qs.last().min_stay
        return ""

    @property
    def max_stay(self):
        qs = self._reservation.prop.availability_set.filter(
            time_frame__overlap=(self._reservation.start_date, self._reservation.end_date)
        )
        if qs.count() == 1:
            return qs.get().min_stay
        if qs.count() > 1:
            qs.exclude(time_frame=(None, None))
            return qs.last().max_stay
        return ""

    @property
    def guest_email(self):
        if self._reservation.guest:
            return self._reservation.guest.email
        return ""

    @property
    def guest_secondary_email(self):
        if self._reservation.guest:
            return self._reservation.guest.secondary_email
        return ""

    @property
    def guest_phone(self):
        if self._reservation.guest:
            return self._reservation.guest.phone
        return ""

    @property
    def guest_secondary_phone(self):
        if self._reservation.guest:
            return self._reservation.guest.secondary_phone
        return ""

    @property
    def agent_email(self):
        return self._user.email

    @property
    def agent_phone(self):
        if self._user.phone:
            return self._user.phone
        return ""

    @cached_property
    def _cleaner_qs(self):
        return User.objects.filter(
            organizations=self._user.organization, account_type=User.VendorTypes.Cleaner.value
        )

    @property
    def cleaner_name(self):
        cleaner = self._cleaner_qs.first()
        return cleaner.get_full_name() if cleaner else ""

    @property
    def cleaner_email(self):
        return self._cleaner_qs.values_list("email", flat=True).first() or ""

    @property
    def cleaner_phone(self):
        return self._cleaner_qs.values_list("phone", flat=True).first() or ""

    @property
    def property_name(self):
        return self._reservation.prop.name

    @property
    def city(self):
        if self._reservation.prop.location:
            return self._reservation.prop.location.city
        return ""

    @property
    def country(self):
        if self._reservation.prop.location:
            return self._reservation.prop.location.country
        return ""

    @property
    def continent(self):
        if self._reservation.prop.location:
            return self._reservation.prop.location.continent
        return ""

    @property
    def region(self):
        if self._reservation.prop.location:
            return self._reservation.prop.location.region
        return ""

    @property
    def state(self):
        if self._reservation.prop.location:
            return self._reservation.prop.location.state
        return ""

    @property
    def postal_code(self):
        return self._reservation.prop.location.postal_code

    @property
    def property_type(self):
        return Property.Types(self._reservation.prop.property_type).pretty_name

    @property
    def rental_type(self):
        return Property.Rentals(self._reservation.prop.rental_type).pretty_name

    @property
    def bedrooms(self):
        return (
            self._reservation.prop.room_set.exclude(beds__contains=["NB"])
            .exclude(beds__len=0)
            .count()
        )

    @property
    def bathrooms(self):
        return self._reservation.prop.room_set.filter(room_type=Room.Types.Bathroom).count()

    @property
    def summary(self):
        try:
            value = self._reservation.prop.descriptions.summary
        except AttributeError:
            value = ""
        return value

    @property
    def description(self):
        try:
            value = self._reservation.prop.descriptions.description
        except AttributeError:
            value = ""
        return value

    @property
    def max_guests(self):
        try:
            value = self._reservation.prop.max_guests or 0
        except AttributeError:
            value = 0
        return value

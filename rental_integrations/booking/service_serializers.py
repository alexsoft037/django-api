import logging
from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal
from functools import partial

from django.utils import timezone
from lxml import etree
from rest_framework import serializers
from rest_framework.fields import empty

logger = logging.getLogger(__name__)


class XMLParser:
    """Default way of parsing XML children in serializers."""

    def to_representation(self, instance):
        def is_many(field):
            return getattr(field, "many", False)

        many_fields = [field for field in self._readable_fields if is_many(field)]
        if many_fields:
            exclude_many = " and ".join(
                "not(self::{})".format(field.field_name) for field in many_fields
            )
            single_children = instance.xpath("./*[{}]".format(exclude_many))
        else:
            single_children = instance.iterchildren()

        value = OrderedDict((element.tag, self._parse_xml(element)) for element in single_children)

        for field in many_fields:
            name = field.field_name
            value[name] = self._parse_xml(instance.iterchildren(name), field=field)

        return value

    def _parse_xml(self, element, field=None):
        if field is None:
            try:
                field = self.fields[element.tag]
            except KeyError:
                logger.info("No tag %s in %s", element.tag, self.__class__.__name__)
                value = None

        if isinstance(field, serializers.BaseSerializer):
            field.instance = element
            value = field.data
        elif isinstance(field, serializers.Field):
            try:
                value = field.to_representation(element.text or "")
            except (TypeError, ValueError) as e:
                logger.info(
                    "Can't repr %s in %s: %s", element.tag, self.__class__.__name__, element.text
                )
                default = field.default
                if default is empty:
                    default = None
                value = default

        return value


class _AvailabilityRateSerializer(serializers.Serializer):

    MAX_STAY = 31
    _StayInteger = partial(serializers.IntegerField, min_value=0, max_value=MAX_STAY)
    _name_mapping = {
        "price": "price",
        "price_for_single": "price1",
        "closed": "closed",
        "closed_on_arrival": "closedonarrival",
        "closed_on_departure": "closedondeparture",
        "min_stay_arrival": "minimumstay_arrival",
        "min_stay": "minimumstay",
        "max_stay_arrival": "maximumstay_arrival",
        "max_stay": "maximumstay",
        "exact_stay": "exactstay",
        "exact_stay_arrival": "exactstay_arrival",
    }

    price = serializers.DecimalField(
        required=False, max_digits=10, decimal_places=2, min_value=Decimal("0.00")
    )
    price_for_single = serializers.DecimalField(
        required=False, max_digits=10, decimal_places=2, min_value=Decimal("0.00")
    )
    closed = serializers.BooleanField(required=False)

    min_stay_arrival = _StayInteger(required=False)
    min_stay = _StayInteger(required=False)
    max_stay_arrival = _StayInteger(required=False)
    max_stay = _StayInteger(required=False)
    exact_stay = _StayInteger(required=False)
    exact_stay_arrival = _StayInteger(required=False)

    closed_on_arrival = serializers.BooleanField(required=False)
    closed_on_departure = serializers.BooleanField(required=False)

    def validate(self, data):
        min_stay_arrival = data.get("min_stay_arrival", 0)
        min_stay = data.get("min_stay", 0)
        max_stay_arrival = data.get("max_stay_arrival", self.MAX_STAY)
        max_stay = data.get("max_stay", self.MAX_STAY)

        if min((min_stay, max_stay, max_stay_arrival)) != min_stay:
            raise serializers.ValidationError(
                "`min_stay` should be smaller than `max_stay` and `max_stay_arrival`"
            )
        elif min((min_stay_arrival, max_stay, max_stay_arrival)) != min_stay_arrival:
            raise serializers.ValidationError(
                "`min_stay_arrival` should be smaller than `max_stay` and `max_stay_arrival`"
            )
        return data

    @classmethod
    def to_xml(cls, data):
        details = etree.Element("rate_details")

        for name, value in data.items():
            e = etree.SubElement(details, cls._name_mapping[name])
            if isinstance(value, bool):
                value = int(value)
            elif isinstance(value, Decimal):
                value = "{:.2f}".format(value)

            e.text = str(value)

        return details


class _AvailabilityDateSerializer(serializers.Serializer):

    from_date = serializers.DateField(required=False)
    to_date = serializers.DateField(required=False)
    dates = serializers.ListField(child=serializers.DateField(), allow_empty=True, required=False)
    rooms_to_sell = serializers.IntegerField(required=False, min_value=0)
    rate_id = serializers.IntegerField(required=False)  # needs to be active
    rate_details = _AvailabilityRateSerializer(required=False)

    DATE_FORMAT = "%Y-%m-%d"

    def validate_from_date(self, from_date):
        if from_date > (timezone.now().date() + timedelta(days=1095)):
            raise serializers.ValidationError("Can be max 3 years from now")
        return from_date

    def validate_to_date(self, to_date):
        if to_date > (timezone.now().date() + timedelta(days=1095)):
            raise serializers.ValidationError("Can be max 3 years from now")
        return to_date

    def validate_dates(self, dates):
        three_years = timezone.now().date() + timedelta(days=1095)
        too_distant = (d for d in dates if d > three_years)
        try:
            next(too_distant)
        except StopIteration:
            pass
        else:
            raise serializers.ValidationError("Can be max 3 years from now")
        return dates

    def validate(self, data):
        from_date = data.pop("from_date", None)
        to_date = data.pop("to_date", None)
        dates = data.pop("dates", None)
        date_attrs = {}

        if from_date and dates:
            raise serializers.ValidationError("Use `dates` and `from_date`, `to_date` exclusively")
        elif from_date is None and dates is None:
            raise serializers.ValidationError("Specify `dates` or both `from_date` and `to_date`")
        elif from_date:
            date_attrs["from"] = from_date.strftime(self.DATE_FORMAT)
            if to_date:
                date_attrs["to"] = to_date.strftime(self.DATE_FORMAT)
        elif dates:
            if len(dates) == 1:
                date_attrs["value"] = dates[0].strftime(self.DATE_FORMAT)
            else:
                str_dates = (d.strftime(self.DATE_FORMAT) for d in dates)
                date_attrs = {"value{}".format(i): date for i, date in enumerate(str_dates, 1)}
        data["date_attrs"] = date_attrs

        rate_provided = "rate_id" in data

        if "rooms_to_sell" in data and rate_provided:
            raise serializers.ValidationError("Specify one of `rate_id` or `rooms_to_sell`")
        elif "rate_details" in data and not rate_provided:
            raise serializers.ValidationError("`rate_details` need `rate_id`")

        return data

    @classmethod
    def to_xml(cls, data):
        date = etree.Element("date", attrib=data["date_attrs"])

        rooms_to_sell = data.get("rooms_to_sell", None)
        rate_id = data.get("rate_id", None)

        if rooms_to_sell is not None:
            to_sell = etree.SubElement(date, "roomstosell")
            to_sell.text = str(rooms_to_sell)

        if rate_id is not None:
            etree.SubElement(date, "rate", id=str(rate_id))

        rate_details = data.get("rate_details", None)
        if rate_details is not None:
            details = _AvailabilityRateSerializer.to_xml(rate_details)
            date.extend(details.getchildren())

        return date


class AvailabilitySerializer(serializers.Serializer):

    room_id = serializers.IntegerField()  # needs to be active
    dates = _AvailabilityDateSerializer(serializers.Serializer, many=True, required=True)

    def save(self):
        return self.to_xml(self.validated_data)

    @classmethod
    def to_xml(cls, data):
        room = etree.Element("room", id=str(data["room_id"]))
        room.extend(map(_AvailabilityDateSerializer.to_xml, data["dates"]))
        return room


class _ReservationCustomerSerializer(XMLParser, serializers.Serializer):

    address = serializers.CharField(default="")
    city = serializers.CharField(default="")
    company = serializers.CharField(default="")
    countrycode = serializers.CharField()
    email = serializers.EmailField(default="")
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    remarks = serializers.CharField(default="")
    telephone = serializers.CharField(default="")
    zip = serializers.CharField(default="")


class _ReservationPriceSerializer(XMLParser, serializers.Serializer):

    price = serializers.DecimalField(max_digits=6, decimal_places=2)
    date = serializers.DateField()
    rate_id = serializers.CharField()

    def to_representation(self, instance):
        value = super().to_representation(instance)
        value.update(
            (name, self.fields[name].to_representation(value))
            for name, value in instance.attrib.items()
            if name in self.fields
        )
        return value


class _ReservationRoomSerializer(XMLParser, serializers.Serializer):

    addons = serializers.CharField(required=False)  # TODO addon serializer
    arrival_date = serializers.DateField()
    commissionamount = serializers.DecimalField(max_digits=6, decimal_places=2)
    currencycode = serializers.CharField()
    departure_date = serializers.DateField()
    extra_info = serializers.CharField()
    facilities = serializers.CharField()
    guest_name = serializers.CharField()
    id = serializers.IntegerField()
    info = serializers.CharField()
    name = serializers.CharField()
    max_children = serializers.IntegerField(required=False)
    meal_plan = serializers.CharField(required=False)
    numberofguests = serializers.IntegerField()
    price = _ReservationPriceSerializer(many=True)
    remarks = serializers.CharField()
    roomreservation_id = serializers.IntegerField()
    smoking = serializers.IntegerField()
    totalprice = serializers.DecimalField(max_digits=6, decimal_places=2)


class ReservationSerializer(XMLParser, serializers.Serializer):

    booked_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S+z")
    commissionamount = serializers.DecimalField(max_digits=6, decimal_places=2)
    currencycode = serializers.CharField()
    customer = _ReservationCustomerSerializer()
    date = serializers.DateField()
    guest_counts = serializers.IntegerField(required=False)
    hotel_id = serializers.CharField()
    hotel_name = serializers.CharField()
    id = serializers.CharField()
    modified_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S+z")
    reservation_extra_info = serializers.CharField()  # TODO extra info serializer
    loyalty_id = serializers.CharField(required=False)
    room = _ReservationRoomSerializer(many=True, required=False)
    status = serializers.ChoiceField(
        choices=(("new", "new"), ("modified", "modified"), ("cancelled", "cancelled"))
    )
    time = serializers.TimeField()
    total_cancellation_fee = serializers.DecimalField(
        max_digits=6, decimal_places=2, required=False
    )
    totalprice = serializers.DecimalField(max_digits=6, decimal_places=2)


class _RoomRateSerializer(serializers.Serializer):

    id = serializers.CharField()
    name = serializers.CharField()
    max_persons = serializers.IntegerField()
    policy_id = serializers.CharField()
    policy = serializers.CharField()

    def to_representation(self, instance):
        attrs = instance.attrib

        return OrderedDict(
            id=attrs["id"],
            name=attrs["rate_name"],
            max_persons=attrs.get("max_persons"),
            policy_id=attrs["policy_id"],
            policy=attrs["policy"],
        )


class RoomSerializer(serializers.Serializer):

    id = serializers.CharField()
    name = serializers.CharField()
    hotel_id = serializers.CharField()
    max_children = serializers.IntegerField(default=0, required=False)

    rates = _RoomRateSerializer(many=True)

    def to_representation(self, instance):
        attrs = instance.attrib
        rates = instance.xpath("./rates/rate")

        return OrderedDict(
            id=attrs["id"],
            name=attrs["room_name"],
            hotel_id=attrs["hotel_id"],
            max_children=attrs.get("max_children", 0),
            rates=_RoomRateSerializer(instance=rates, many=True).data,
        )


class PropertySearchSerializer(serializers.Serializer):

    id = serializers.CharField()
    name = serializers.CharField()

    def to_representation(self, instance):
        attrs = instance.attrib
        return OrderedDict(id=attrs["HotelCode"], name=attrs["HotelName"])

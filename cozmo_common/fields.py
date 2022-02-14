from functools import partial
from inspect import isclass

import phonenumbers
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.exceptions import ValidationError
from rest_framework.fields import CharField, CurrentUserDefault, Field, ReadOnlyField, empty
from rest_framework.relations import RelatedField
from rest_framework.serializers import Field as SerializerField

from cozmo_common.enums import ChoicesMixin
from cozmo_common.utils import format_decimal_to_str, get_dt_from_timestamp
from notifications.utils import to_e164
from .validators import HourValidator, PhoneValidator

OptionalCharField = partial(CharField, allow_null=True, allow_blank=True, default="")


class ChoicesField(Field):
    """Uses values of choices to communicate in API and keys to store in database."""

    def __init__(self, choices, **kwargs) -> object:
        if isclass(choices) and issubclass(choices, ChoicesMixin):
            choices = choices.choices()
        self._choices = dict(choices)
        super().__init__(**kwargs)

    def to_representation(self, obj):
        return self._choices.get(obj, obj)

    def to_internal_value(self, data):
        if not data and not self.required:
            return data

        for k, v in dict(self._choices).items():
            if v == data:
                return k

        raise ValidationError(
            "Invalid value: {}. Choices are: {}".format(data, ", ".join(self._choices.values()))
        )


class PositiveSmallIntegerChoicesField(SerializerField):
    """Uses values of choices to communicate in API and keys to store in database."""

    def __init__(self, choices, **kwargs) -> object:
        if isclass(choices) and issubclass(choices, ChoicesMixin):
            choices = choices.choices()
        self._choices = dict(choices)
        super().__init__(**kwargs)

    def to_representation(self, obj):
        return self._choices.get(obj, None)

    def to_internal_value(self, data):
        for k, v in dict(self._choices).items():
            if v == data:
                return k

        raise ValidationError(
            "Invalid value: {}. Choices are: {}".format(data, ", ".join(self._choices.values()))
        )


class ModelChoicesField(ChoicesField):
    def to_representation(self, obj):
        return obj._meta.object_name


class ContextDefault:
    def __init__(self, context_key):
        self._key = context_key
        self.data = None

    def set_context(self, serializer_field):
        try:
            self.data = serializer_field.context[self._key]
        except KeyError:
            self.data = None

    def __call__(self):
        return self.data


class DefaultOrganization:
    def set_context(self, serializer_field):
        try:
            self.organization = serializer_field.context["request"].user.organization
        except KeyError:
            self.organization = serializer_field.context["organization"]

    def __call__(self):
        return self.organization


class RequestUser:
    def set_context(self, serializer_field):
        try:
            self.request_user = serializer_field.context["request"].user
        except KeyError:
            self.request_user = None

    def __call__(self):
        return self.request_user


class HourField(CharField):
    """Field for storing hour in HH:MM format."""

    def __init__(self, *args, **kwargs):
        super().__init__(**kwargs)
        self.validators.append(HourValidator())


class NestedRelatedField(RelatedField):
    """Field for changing related object by id and returning serialized value."""

    lookup_field = "id"
    serializer = None

    default_error_messages = {
        "invalid": "Invalid value.",
        "does_not_exist": "Object with {lookup_field}={value} does not exist.",
    }

    def __init__(self, **kwargs):
        self.lookup_field = kwargs.pop("lookup_field", self.lookup_field)
        self.serializer = kwargs.pop("serializer", self.serializer)
        super().__init__(**kwargs)

    def to_representation(self, obj):
        if self.serializer:
            data = self.serializer(instance=obj, context=self.context).data
        else:
            data = {self.lookup_field: obj.pk}
        return data

    def to_internal_value(self, data):
        if data is None and self.allow_null:
            return None
        try:
            return self.get_queryset().get(**{self.lookup_field: data})
        except (TypeError, ValueError):
            self.fail("invalid")
        except ObjectDoesNotExist:
            self.fail("does_not_exist", lookup_field=self.lookup_field, value=data)


class PhoneField(CharField):
    def __init__(self, **kwargs):
        kwargs.pop("min_length", None)
        kwargs.pop("max_length", None)
        super().__init__(**kwargs)
        self.validators.append(PhoneValidator())


class E164PhoneField(PhoneField):

    default_error_messages = {
        'invalidnumber': '"{input}" is not a valid number.'
    }

    def to_internal_value(self, data):
        return to_e164(data)

    def run_validation(self, data=empty):
        is_valid = super(PhoneField, self).run_validation(data)

        if is_valid:
            number = phonenumbers.parse(data, "US")
            if not phonenumbers.is_possible_number(number):
                self.fail("invalidnumber", input=data)
        return is_valid


class AppendField:
    def __init__(self, obj, field_name, value):
        self.obj = obj
        self.field_name = field_name
        self.value = value

    def __enter__(self):
        setattr(self.obj, self.field_name, self.value)
        return self

    def __exit__(self, *args):
        delattr(self.obj, self.field_name)


class AppendFields:
    def __init__(self, obj, field_name_mapping):
        self.obj = obj
        self.field_name_mapping = field_name_mapping

    def __enter__(self):
        [setattr(self.obj, name, value) for name, value in self.field_name_mapping.items()]
        return self

    def __exit__(self, *args):
        [delattr(self.obj, name) for name in self.field_name_mapping]


class DefaultUser(CurrentUserDefault):
    def set_context(self, serializer_field):
        try:
            self.user = serializer_field.context["request"].user
        except KeyError:
            self.user = serializer_field.context["user"]

    def __call__(self):
        return self.user


class EpochTimestampField(ReadOnlyField):
    """
    Read-only timestamp field that converts an epoch timestamp to datetime
    """

    def to_representation(self, value):
        return get_dt_from_timestamp(value)


class IntegerMoneyField(Field):
    """
    Converts integer based decimal/money values to a string-decimal value
    """

    def to_representation(self, value):
        return format_decimal_to_str(value / 100)

    def to_internal_value(self, data):
        return float(data) * 100

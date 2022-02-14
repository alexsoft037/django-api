from rest_framework.exceptions import ValidationError
from rest_framework.fields import Field
from rest_framework.relations import RelatedField

from . import models


class EnumField(Field):
    """Uses names of Enum to communicate in API and values to store in database."""

    def __init__(self, enum_klass, **kwargs):
        self._enum = enum_klass
        super().__init__(**kwargs)

    def to_representation(self, obj):
        try:
            value = self._enum(obj).name
        except ValueError:
            value = None
        return value

    def to_internal_value(self, data):
        try:
            value = self._enum[data]
        except KeyError:
            raise ValidationError(
                "Invalid value: {}. Choices are: {}".format(
                    data, ", ".join(e.name for e in self._enum)
                )
            )
        return value


class TagRelatedField(RelatedField):

    queryset = models.Tag.objects.all()

    def to_representation(self, value):
        if not isinstance(value, models.Tag):
            raise ValueError("Unexpected type of tag object")
        return value.name

    def to_internal_value(self, data):
        return models.Tag(name=data)

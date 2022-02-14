from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from rest_framework.exceptions import ValidationError
from rest_framework.fields import IntegerField, ListField, SerializerMethodField
from rest_framework.serializers import ListSerializer, ModelSerializer, Serializer

from listings.choices import Currencies
from .fields import ChoicesField


class CustomListSerializer(ListSerializer):
    def create(self, validated_data, **kwargs):
        for i, data in enumerate(validated_data):
            data.update(kwargs)
        return super().create(validated_data)


class OrderSerializer(Serializer):

    order = ListField(child=IntegerField())

    lookup_field = "id"
    order_field = "order"

    def __init__(self, *args, prop_id=None, **kwargs):
        super().__init__(*args, **kwargs)

        assert hasattr(self, "Meta"), 'Class {serializer_class} missing "Meta" attribute'.format(
            serializer_class=self.__class__.__name__
        )
        assert hasattr(
            self.Meta, "model"
        ), 'Class {serializer_class} missing "Meta.model" attribute'.format(
            serializer_class=self.__class__.__name__
        )

        self.prop_id = prop_id

    def validate_order(self, order):
        qs = self.Meta.model.objects.filter(prop_id=self.prop_id)

        if len(set(order)) != len(order):
            raise ValidationError("Elements should be unique")
        if qs.count() != len(order):
            raise ValidationError("Choose all elements of this property")
        if qs.filter(**{self.lookup_field + "__in": order}).count() != len(order):
            raise ValidationError("Choose only elements of this property")

        return order

    def create(self, validated_data):
        ids = validated_data["order"]

        with transaction.atomic():
            for i, element_id in enumerate(ids):
                self.Meta.model.objects.filter(**{self.lookup_field: element_id}).update(
                    **{self.order_field: i}
                )
        return ids


class ValueFormattedSerializer(ModelSerializer):
    value_formatted = SerializerMethodField()
    serializer_choice_field = ChoicesField

    def get_value_formatted(self, obj):
        try:
            currency = obj.reservation.prop.pricing_settings.currency
        except ObjectDoesNotExist:
            currency = Currencies.USD.pretty_name
        return "{0}{1:.2f}".format(Currencies[currency].symbol, obj.value)

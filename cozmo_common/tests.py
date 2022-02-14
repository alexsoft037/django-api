from datetime import date
from unittest import mock

from django.core.exceptions import ValidationError as DjValidationError
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from cozmo_common.enums import ChoicesEnum
from cozmo_common.utils import get_ical_friendly_date
from .db.fields import PhoneField
from .fields import ChoicesField
from .filters import OrganizationFilter

DATETIME_ISOFORMAT_RET_VALUE = "2019-03-07"
DATETIME_RETURN_VALUE = "20190307"


class PhoneFieldTestCase(TestCase):
    def test_run_validators(self):
        field = PhoneField()

        for valid_number in (None, "", "+12345", "12345", "+123456789012345", "123456789012345"):
            with self.subTest(number=valid_number, msg="Valid numbers"):
                self.assertIsNone(field.run_validators(valid_number), "This should not raise")

        for invalid_number in (
            "1234",
            "+1234",
            "+012345",
            "012345",
            "+1234567890123456",
            "1234567890123456",
        ):
            with self.subTest(number=invalid_number, msg="Invalid numbers"), (
                self.assertRaises(DjValidationError)
            ):
                field.run_validators(invalid_number)


class OrganizationFilterTestCase(TestCase):
    def test_filter_queryset(self):
        organization_filter = OrganizationFilter()
        request = mock.MagicMock()
        queryset = mock.MagicMock()
        view = None
        organization_filter.filter_queryset(request, queryset, view)
        queryset.filter.assert_called_once_with(organization=request.user.organization)


class ChoicesFieldTestCase(TestCase):
    field_class = ChoicesField

    @classmethod
    def setUpTestData(cls):
        cls.enum = ChoicesEnum("TestEnum", {"field": "value"})

    def test_tuple_choices(self):
        field = self.field_class(choices=self.enum.choices())
        self.assertEqual(field.to_internal_value("field"), self.enum.field.value)

    def test_enum_choices(self):
        field = self.field_class(choices=self.enum)
        self.assertEqual(field.to_internal_value("field"), self.enum.field.value)

    def test_value_not_present_in_choices(self):
        choices = {}
        field = self.field_class(choices=choices)
        obj = "not in choices"
        self.assertNotIn(obj, choices)
        self.assertEqual(field.to_representation(obj), obj)

    def test_allow_empty_string(self):
        data = ""

        with self.subTest("Allow when not required"):
            field = self.field_class(choices=self.enum, required=False)
            self.assertEqual(field.to_internal_value(data), data)

        with self.subTest("Not allow when required"):
            field = self.field_class(choices=self.enum, required=True)
            with self.assertRaises(ValidationError):
                field.to_internal_value(data)


class UtilTestCase(TestCase):
    def test_ical_util(self):
        value = get_ical_friendly_date(date(year=2019, month=3, day=7))
        self.assertEquals(value, DATETIME_RETURN_VALUE)

from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.serializers import ListSerializer

from accounts.models import Organization
from crm.models import Contact
from listings import models, serializers, views
from listings.choices import CalculationMethod
from listings.public_views import InquiryView

User = get_user_model()


class ChargeViewTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.prop_count = 2
        cls.organization = Organization.objects.create()

        cls.props = models.Property.objects.bulk_create(
            models.Property(
                name="Name {}".format(i),
                property_type=models.Property.Types.Apartment.value,
                rental_type=models.Property.Rentals.Private.value,
                status=models.Property.Statuses.Active.value,
                organization=cls.organization,
            )
            for i in range(cls.prop_count)
        )

    def test_get(self):
        kwargs = {"user.organization": self.organization, "query_params.get.return_value": None}
        request = mock.MagicMock(**kwargs)
        view = views.ChargeView(format_kwarg=None, request=request)

        resp = view.list(request)
        self.assertEqual(len(list(resp.data)), self.prop_count)

    def test_get_charge(self):
        request = mock.MagicMock()
        view = views.ChargeView(request=request, format_kwarg=None)
        charges = view._get_charge(self.props[0].id)
        self.assertIsInstance(charges, dict)

    def test_get_filtered(self):
        kwargs = {
            "user.organization": self.organization,
            "query_params.get.return_value": self.props[0].pk,
        }
        request = mock.MagicMock(**kwargs)
        view = views.ChargeView(format_kwarg=None, request=request)

        resp = view.list(request)
        self.assertEqual(len(list(resp.data)), 1)

    def test_invalid_pk(self):
        non_existing_pk = -1
        kwargs = {"user.organization": None, "query_params.get.return_value": non_existing_pk}
        request = mock.MagicMock(**kwargs)
        view = views.ChargeView(format_kwarg=None, request=request)

        with self.assertRaises(NotFound):
            view.list(request)


class PointOfInterestViewSetTestCase(TestCase):
    def test_create_many(self):
        view_kwargs = {"action": "create", "request": mock.MagicMock(), "format_kwarg": None}
        view = views.PointOfInterestViewSet(**view_kwargs)
        serializer = view.get_serializer(data=[{"some": "data"}, {"another": "data"}])
        self.assertIsInstance(serializer, ListSerializer)


class PropertyViewSetTestCase(TestCase):
    def setUp(self):
        self.view = views.PropertyViewSet(
            kwargs={}, request=mock.MagicMock(**{"query_params": {}, "user.organization": None})
        )

    @mock.patch("listings.views.GroupAccessFilter.filter_queryset", return_value=[])
    def test_get_serializer_class(self, mock_filter):
        with self.subTest(msg="Serializer for partial_update"):
            self.view.action = "partial_update"
            serializer_class = self.view.get_serializer_class()
            self.assertIs(serializer_class, serializers.PropertyUpdateSerializer)

        with self.subTest(msg="Serializer for update"):
            self.view.action = "update"
            serializer_class = self.view.get_serializer_class()
            self.assertIs(serializer_class, serializers.PropertyCreateSerializer)

        with self.subTest(msg="Serializer for create"):
            self.view.action = "create"
            serializer_class = self.view.get_serializer_class()
            self.assertIs(serializer_class, serializers.PropertyCreateSerializer)

        with self.subTest(msg="Serializer for list"):
            self.view.action = "list"
            serializer_class = self.view.get_serializer_class()
            self.assertIs(serializer_class, serializers.PropertyListSerializer)

        with self.subTest(msg="Default serializer"):
            self.view.action = "any other action"
            serializer_class = self.view.get_serializer_class()
            self.assertIs(serializer_class, serializers.PropertySerializer)

        with self.subTest(msg="Serializer for `basic` filter"):
            self.view.action = "any other action"
            self.view.request.query_params = {"basic": "true"}
            self.view.filter_queryset(self.view.get_queryset())
            serializer_class = self.view.get_serializer_class()
            self.assertIs(serializer_class, serializers.PropertyMinimalSerializer)


class RateViewSetTestCase(TestCase):
    def test_filter_by_prop(self):
        Property = models.Property
        organization = Organization.objects.create()

        prop = Property.objects.create(
            name="Name",
            property_type=Property.Types.Apartment.value,
            rental_type=Property.Rentals.Private.value,
            organization=organization,
        )
        other_prop = Property.objects.create(
            name="Other name",
            property_type=Property.Types.Apartment.value,
            rental_type=Property.Rentals.Private.value,
            organization=organization,
        )
        other_prop.rate_set.add(
            models.Rate.objects.create(nightly=10, time_frame=(None, None), prop=other_prop)
        )
        self.assertEqual(prop.rate_set.all().count(), 0)
        self.assertEqual(other_prop.rate_set.all().count(), 1)

        view = views.RateViewSet()
        attrs = {"user.organization": organization, "query_params.get.return_value": prop.pk}
        view.request = mock.MagicMock(**attrs)
        qs = view.get_queryset()
        qs = view.filter_queryset(qs)
        self.assertEqual(qs.count(), 0)


class ReservationViewSetTestCase(TestCase):
    @mock.patch(
        "listings.views.ReservationViewSet.get_serializer",
        side_effect=mock.MagicMock(spec=serializers.GuestSerializer),
    )
    @mock.patch("listings.views.ReservationViewSet.get_object")
    def test_guest(self, m_get_object, m_get_serializer):
        pk = 0
        request = mock.MagicMock(data={})
        view = views.ReservationViewSet(action="patch", request=request)

        with self.subTest(msg="Guest exists"):
            m_get_object.return_value = mock.MagicMock(guest=Contact())
            view.guest(request, pk)

        with self.subTest(msg="No guest"), self.assertRaises(Http404):
            m_get_object.return_value = mock.MagicMock(spec=models.Reservation)
            type(m_get_object.return_value).guest = mock.PropertyMock(
                side_effect=ObjectDoesNotExist
            )
            view.guest(request, pk)

    def test_get_serializer_context(self):
        view = views.ReservationViewSet(request=mock.Mock(), format_kwarg=None)
        self.assertIn("organization", view.get_serializer_context())

    def test_get_serializer(self):
        view = views.ReservationViewSet(request=mock.Mock(), format_kwarg=None)
        serializer = view.get_serializer()
        self.assertTrue(serializer.skip_ipa_validation)

        with mock.patch.object(
            view, "get_serializer_class", return_value=serializers.GuestSerializer
        ):
            serializer = view.get_serializer()
            self.assertFalse(hasattr(serializer, "skip_ipa_validation"))


class GroupViewSetTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create()
        cls.group = models.Group.objects.create(organization=cls.organization)
        cls.properties = models.Property.objects.bulk_create(
            models.Property(organization=cls.organization) for i in range(2)
        )

    def test_assign_properties(self):
        kwargs = {
            "user.organization": self.organization,
            "data": [p.id for p in self.properties],
            "kwargs": {"pk": self.group.id},
        }

        request = mock.MagicMock(**kwargs)

        view = views.GroupViewSet(action="PUT", request=request)
        view.kwargs = {"pk": self.group.id}
        response = view.assign_properties(request, self.group.id)
        self.assertEqual(response.data, {"assigned": 2})


class QuoteViewSetTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create()
        cls.prop = models.Property.objects.create(
            name="Name",
            property_type=models.Property.Types.Apartment.value,
            rental_type=models.Property.Rentals.Private.value,
            status=models.Property.Statuses.Active.value,
            organization=cls.organization,
        )
        models.PricingSettings.objects.create(nightly=Decimal("100"), prop=cls.prop)

        cls.prop2 = models.Property.objects.create(
            name="Prop2 Name",
            property_type=models.Property.Types.Apartment.value,
            rental_type=models.Property.Rentals.Private.value,
            status=models.Property.Statuses.Active.value,
            organization=cls.organization,
        )

        cls.start = timezone.now().date()
        cls.end = timezone.now().date() + timedelta(days=10)

        models.Rate.objects.create(
            nightly=Decimal("200"),
            time_frame=(cls.start, cls.end + timedelta(days=2)),
            prop=cls.prop,
        )
        models.AdditionalFee.objects.create(
            value=1,
            optional=False,
            calculation_method=CalculationMethod.Daily.value,
            prop=cls.prop,
        )

        models.AdditionalFee.objects.create(
            value=1,
            optional=False,
            calculation_method=CalculationMethod.Per_Stay.value,
            prop=cls.prop,
        )

        models.AdditionalFee.objects.create(
            value=1,
            optional=False,
            calculation_method=CalculationMethod.Per_Person_Per_Day.value,
            prop=cls.prop,
        )

        models.AdditionalFee.objects.create(
            value=10,
            optional=False,
            calculation_method=CalculationMethod.Per_Person_Per_Stay.value,
            prop=cls.prop,
        )

        models.AdditionalFee.objects.create(
            value=2,
            optional=False,
            calculation_method=CalculationMethod.Per_Stay_Percent.value,
            prop=cls.prop,
        )

        models.AdditionalFee.objects.create(
            value=2,
            optional=False,
            calculation_method=CalculationMethod.Per_Stay_Only_Rates_Percent.value,
            prop=cls.prop,
        )

        models.AdditionalFee.objects.create(
            value=2,
            optional=False,
            calculation_method=CalculationMethod.Per_Stay_No_Taxes_Percent.value,
            prop=cls.prop,
        )

        models.Discount.objects.create(
            value=2,
            prop=cls.prop,
            is_percentage=False,
            days_before=10,
            discount_type=models.Discount.Types.Late_Bird.value,
            calculation_method=CalculationMethod.Per_Stay.value,
        )

        models.Blocking.objects.create(
            time_frame=(cls.end + timedelta(days=40), None), summary="Some fixes", prop=cls.prop
        )

    def test_list(self):
        kwargs = {"user.organization": self.organization}

        with self.subTest(msg="Period is not blocked"):
            kwargs.update(
                {"query_params": {"prop": self.prop.id, "adults": 1, "children": 2, "pets": 1}}
            )
            request = mock.MagicMock(**kwargs)

            view = views.QuoteViewSet()
            view.request = request
            view.kwargs = {"prop_id": self.prop.id}
            resp_data = view.list(request, self.prop.id).data

            self.assertEqual(resp_data["adults"], 1)
            self.assertEqual(resp_data["children"], 2)
            self.assertEqual(resp_data["pets"], 1)
            self.assertTrue(resp_data["available"])
            self.assertEqual(len(resp_data["fees"]), 7)
            self.assertEqual(len(resp_data["discounts"]), 1)
            # FIXME Should we include base price in "rates" or in new field?
            self.assertEqual(resp_data["arrival_date"], self.start)
            self.assertEqual(resp_data["departure_date"], self.start + timedelta(days=30))
            self.assertEqual(resp_data["nights"], 30)
            self.assertEqual(resp_data["currency"], "USD")
            self.assertEqual(resp_data["price"], "4482.24")

        with self.subTest(mag="Period is blocked"):

            kwargs.update(
                {
                    "query_params": {
                        "prop": self.prop.id,
                        "prop_id": self.prop.id,
                        "adults": 1,
                        "children": 2,
                        "pets": 1,
                        "from": str(self.start + timedelta(days=41)),
                    }
                }
            )

            request = mock.MagicMock(**kwargs)

            view = views.QuoteViewSet()
            view.kwargs = {"prop_id": self.prop.id}
            view.request = request
            resp_data = view.list(request, self.prop.id).data

            self.assertFalse(resp_data["available"])
            self.assertIn("price", resp_data)

        with self.subTest(msg="Property does not have rates"):
            start_date = self.start + timedelta(days=41)
            end_date = start_date + timedelta(days=30)
            kwargs.update(
                {
                    "query_params": {
                        "prop": self.prop2.id,
                        "prop_id": self.prop2.id,
                        "adults": 1,
                        "children": 2,
                        "pets": 1,
                        "from": str(start_date),
                    }
                }
            )

            request = mock.MagicMock(**kwargs)

            view = views.QuoteViewSet()
            view.kwargs = {"prop_id": self.prop2.id}
            view.request = request
            resp = view.list(request, self.prop.id)
            self.assertEqual(resp.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
            self.assertEqual(
                resp.data,
                {
                    "adults": kwargs["query_params"]["adults"],
                    "arrival_date": start_date,
                    "available": False,
                    "children": kwargs["query_params"]["children"],
                    "departure_date": end_date,
                    "nights": (end_date - start_date).days,
                    "pets": kwargs["query_params"]["pets"],
                },
            )


class InquiryViewTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = models.Organization.objects.create()
        cls.prop = models.Property.objects.create(
            name="Name",
            property_type=models.Property.Types.Apartment.value,
            rental_type=models.Property.Rentals.Private.value,
        )
        cls.guest = Contact.objects.create(organization=cls.org)
        cls.reservation = models.Reservation.objects.create(
            start_date=date(2018, 6, 4),
            end_date=date(2018, 6, 13),
            price=Decimal("0"),
            paid=Decimal("0.00"),
            prop=cls.prop,
            expiration=timezone.now() + timedelta(days=7),
            guest=cls.guest,
            status=models.Reservation.Statuses.Inquiry_Blocked.value,
        )

    def test_get_object(self):

        request = mock.MagicMock()
        request.token_payload = {"type": "Reservation", "id": self.reservation.id}

        view = InquiryView()
        view.request = request
        instance = view.get_object()
        self.assertEqual(self.reservation, instance)

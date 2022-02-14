from datetime import date, timedelta
from decimal import Decimal
from operator import attrgetter
from random import choice
from unittest import mock
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone
from rest_framework.compat import coreapi
from rest_framework.exceptions import NotFound

from cozmo_common.filters import OrganizationFilter
from listings import filters, models
from listings.choices import PropertyStatuses


class GetSchemaFieldsTestCase(TestCase):
    def test_get_schema_fields(self):
        view = mock.MagicMock()
        filter_backends = (
            filters.IdFilter,
            filters.PropertyIdFilter,
            filters.ReservationDateFilter,
            OrganizationFilter,
        )

        for BackendClass in filter_backends:
            with self.subTest(msg=BackendClass.__class__.__name__):
                fields = BackendClass().get_schema_fields(view)

                for field in fields:
                    self.assertIsInstance(field, coreapi.Field)


class MultiReservationFilterTest(TestCase):
    def test_query(self):
        filter_backend = filters.MultiReservationFilter()

        request = mock.MagicMock(query_params={"query": "some query"})
        queryset = models.Reservation.objects.none()
        view = mock.MagicMock()

        filtered_qs = filter_backend.filter_queryset(request, queryset, view)
        self.assertEqual(queryset.count(), filtered_qs.count())

    def test_reservation_start_and_end_date_query(self):
        start_date = "2018-01-03"
        end_date = "2018-01-05"
        filter_backend = filters.MultiReservationFilter()
        request = mock.MagicMock(query_params={"startDate": start_date, "endDate": end_date})
        queryset = mock.MagicMock()
        queryset.filter.return_value = queryset
        queryset.count.return_value = 1
        view = mock.MagicMock()
        view.action = "list"
        filtered_qs = filter_backend.filter_queryset(request, queryset, view)

        queryset.filter.assert_called_with(
            start_date__gte=start_date,
            start_date__lte=end_date,
        )
        self.assertEqual(queryset.count(), filtered_qs.count())

    def test_reservation_start_date_only_query(self):
        start_date = "2018-01-03"
        filter_backend = filters.MultiReservationFilter()
        request = mock.MagicMock(query_params={"startDate": start_date})
        queryset = mock.MagicMock()
        queryset.filter.return_value = queryset
        queryset.count.return_value = 1
        view = mock.MagicMock()
        view.action = "list"
        filtered_qs = filter_backend.filter_queryset(request, queryset, view)

        queryset.filter.assert_called_with(
            start_date__gte=start_date,
        )
        self.assertEqual(queryset.count(), filtered_qs.count())


class ReservationDateFilterTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.res_filter = filters.ReservationDateFilter()
        models.Property.objects.all().delete()
        cls.prop = models.Property.objects.create(
            name="Name",
            property_type=models.Property.Types.Apartment.value,
            rental_type=models.Property.Rentals.Private.value,
        )
        cls.other_prop = models.Property.objects.create(
            name="Name",
            property_type=models.Property.Types.Apartment.value,
            rental_type=models.Property.Rentals.Private.value,
        )

    def test_normalize_dates(self):
        with self.subTest(msg="Both unset"):
            start, end = None, None
            norm_start, norm_end = self.res_filter._normalize_dates(start, end)
            self.assertIsInstance(norm_start, date)
            self.assertEqual(norm_end, norm_start + timedelta(self.res_filter.MAX_PERIOD))

        with self.subTest(msg="End unset"):
            start = timezone.now().date() + timedelta(days=10)
            end = None
            norm_start, norm_end = self.res_filter._normalize_dates(start, end)
            self.assertEqual(norm_start, start)
            self.assertEqual(norm_end, norm_start + timedelta(self.res_filter.MAX_PERIOD))

        with self.subTest(msg="Start unset"):
            start = None
            end = timezone.now().date() + timedelta(days=10)
            norm_start, norm_end = self.res_filter._normalize_dates(start, end)
            self.assertEqual(norm_end, end)
            self.assertEqual(norm_start, norm_end - timedelta(self.res_filter.MAX_PERIOD))

        with self.subTest(msg="Both set"):
            start = timezone.now().date()
            end = timezone.now().date() + timedelta(days=10)
            norm_start, norm_end = self.res_filter._normalize_dates(start, end)
            self.assertEqual(norm_start, start)
            self.assertEqual(norm_end, end)

    def test_validate_dates(self):
        with self.subTest(msg="Valid period"):
            start = timezone.now().date()
            end = start + timedelta(days=2)
            validated = self.res_filter._validate_dates(start, end)
            self.assertEqual(validated, (start, end))

        with self.subTest(msg="Invalid period"):
            start = timezone.now().date()
            end = start - timedelta(days=2)

            with self.assertRaises(NotFound):
                self.res_filter._validate_dates(start, end)

    def test_get_query_params(self):
        request = mock.MagicMock()

        invalid_formats = ["20171231", "2017.12.31", "2017.31.12", "2017 dec 31"]

        for date_format in invalid_formats:
            with self.subTest(msg="Invalid start format", date_format=date_format):
                request.query_params = {"from": date_format}
                with self.assertRaises(NotFound):
                    self.res_filter.get_query_params(request)

            with self.subTest(msg="Invalid end format", date_format=date_format):
                request.query_params = {"to": date_format}
                with self.assertRaises(NotFound):
                    self.res_filter.get_query_params(request)

        with mock.patch.object(self.res_filter, "_normalize_dates", return_value=("from", "to")), (
            mock.patch.object(self.res_filter, "_validate_dates", return_value=("from", "to"))
        ):
            request.query_params = {}
            self.res_filter.get_query_params(request)

    def test_filter_queryset(self):
        start = timezone.now().date()
        end = start + timedelta(days=10)

        models.Reservation.objects.all().delete()

        included = models.Reservation.objects.bulk_create(
            (
                models.Reservation(
                    start_date=start + timedelta(days=1),
                    end_date=end - timedelta(days=1),
                    price=Decimal("0"),
                    paid=Decimal("0.00"),
                    prop_id=self.prop.pk,
                ),
                models.Reservation(
                    start_date=start - timedelta(days=10),
                    end_date=start,
                    price=Decimal("0"),
                    paid=Decimal("0.00"),
                    prop_id=self.prop.pk,
                ),
                models.Reservation(
                    start_date=end,
                    end_date=end + timedelta(days=10),
                    price=Decimal("0"),
                    paid=Decimal("0.00"),
                    prop_id=self.prop.pk,
                ),
            )
        )
        excluded = models.Reservation.objects.bulk_create(
            (
                models.Reservation(
                    start_date=start - timedelta(days=10),
                    end_date=start - timedelta(days=1),
                    price=Decimal("0"),
                    paid=Decimal("0.00"),
                    prop_id=self.prop.pk,
                ),
                models.Reservation(
                    start_date=end + timedelta(days=1),
                    end_date=end + timedelta(days=10),
                    price=Decimal("0"),
                    paid=Decimal("0.00"),
                    prop_id=self.prop.pk,
                ),
                models.Reservation(
                    start_date=end + timedelta(days=1),
                    end_date=end + timedelta(days=10),
                    price=Decimal("0"),
                    paid=Decimal("0.00"),
                    prop_id=self.other_prop.pk,
                ),
            )
        )

        with mock.patch.object(self.res_filter, "get_query_params", return_value=(start, end)):
            qs = self.res_filter.filter_queryset(
                request=mock.MagicMock(),
                queryset=models.Property.objects.all(),
                view=mock.MagicMock(),
            )

        self.assertEqual(qs.count(), models.Property.objects.all().count())
        reservations = qs[0].reservation_included
        self.assertListEqual(
            sorted(reservations, key=attrgetter("id")), sorted(included, key=attrgetter("id"))
        )
        self.assertTrue(set(reservations).isdisjoint(excluded))


class StatusFilterTestCase(TestCase):
    def test_filter_queryset(self):
        filter_backend = filters.StatusFilter()
        queryset = mock.Mock(spec=models.Property.objects)
        request = mock.Mock()
        view = mock.Mock(action="list")

        with self.subTest("Invalid status name"):
            status = "invalid-status-name"
            request.query_params = {"status": status}
            with self.assertRaises(KeyError):
                PropertyStatuses[status]
            queryset.reset_mock()
            filter_backend.filter_queryset(request, queryset, view)
            # queryset.filter.assert_called_once_with(status=PropertyStatuses.Active)

        with self.subTest("No status name"):
            status = None
            request.query_params = {"status": status}
            with self.assertRaises(KeyError):
                PropertyStatuses[status]
            queryset.reset_mock()
            filter_backend.filter_queryset(request, queryset, view)
            # queryset.filter.assert_called_once_with(status=PropertyStatuses.Active)

        with self.subTest("Correct status"):
            status = choice(list(s.pretty_name for s in PropertyStatuses))
            request.query_params = {"status": status}
            queryset.reset_mock()
            filter_backend.filter_queryset(request, queryset, view)
            queryset.filter.assert_called_once_with(status=PropertyStatuses[status])

        for action in ("retrieve", "delete", "update", "partial_update"):
            status = "invalid-status-name"
            request.query_params = {"status": status}
            view.action = action
            with self.subTest(f"Don't use default value on {action}"):
                queryset.reset_mock()
                filter_backend.filter_queryset(request, queryset, view)
                queryset.filter.assert_not_called()


class MultiCalendarFilterTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        models.Property.objects.bulk_create(
            models.Property(
                name=uuid4().hex,
                property_type=models.Property.Types.Apartment.value,
                rental_type=models.Property.Rentals.Private.value,
                max_guests=i,
                pricing_settings=models.PricingSettings.objects.create(nightly=10),
            )
            for i in range(1, 4)
        )

    def test_filter_queryset(self):
        queryset = models.Property.objects.all()
        request = mock.MagicMock()
        view = mock.MagicMock()

        self.assertEqual(3, queryset.count())

        with self.subTest("Filter capacity"):
            request.query_params = {"capacity": "3"}
            mc = filters.MultiCalendarFilter()
            result = mc.filter_queryset(request, queryset, view)
            self.assertEqual(1, len(result))

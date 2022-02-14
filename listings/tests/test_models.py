from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone
from psycopg2.extras import DateRange

from accounts.models import Organization
from accounts.profile.models import PlanSettings
from cozmo.storages import AzureStorage
from crm.models import Contact
from listings import models
from listings.choices import CalculationMethod, CancellationPolicy, WeekDays
from rental_connections.models import RentalConnection


class PropertyTestCase(TestCase):
    def test_sync(self):
        status = models.Property.Statuses.Active

        p = models.Property.objects.create(
            name="Name",
            property_type=models.Property.Types.Apartment.value,
            rental_type=models.Property.Rentals.Private.value,
            status=status,
        )

        with self.subTest("Fail silently when no rental_connection"):
            self.assertIsNone(p.rental_connection)
            p.sync()
            self.assertEqual(p.status, status)

        with self.subTest("Disable prop when no access to external listing"):
            conn = RentalConnection.objects.create()
            conn.sync = mock.Mock(side_effect=models.ServiceException)
            p.rental_connection = conn
            p.sync()
            self.assertEqual(p.status, models.Property.Statuses.Disabled)


class RateTestCase(TestCase):

    MONTH_DAYS = 30
    BASE_PRICE = Decimal("100.00")
    MONTHLY_PRICE = BASE_PRICE * 30 * Decimal("0.8")
    WEEKEND_PRICE = BASE_PRICE * Decimal("1.2")
    WEEKLY_PRICE = BASE_PRICE * 7 * Decimal("0.9")

    @classmethod
    def setUpTestData(cls):
        cls.prop = models.Property.objects.create(
            name="Name",
            property_type=models.Property.Types.Apartment.value,
            rental_type=models.Property.Rentals.Private.value,
        )

    def setUp(self):
        self.prop.rate_set.all().delete()

    def calc_price_for_days(self, start_date, days):
        days_price = 0
        weekend = [WeekDays.Sunday, WeekDays.Saturday]
        for i in range(0, days):
            current = start_date + timedelta(days=i)
            if current.weekday() in weekend:
                price = self.WEEKEND_PRICE
            else:
                price = self.BASE_PRICE
            days_price += price
        return days_price

    def test_calc_price_for_days(self):
        with self.subTest("Weekday and weekend days"):
            end_date = date.today()
            end_date += timedelta(days=7 - end_date.weekday())
            start_date = end_date - timedelta(days=3)

            self.assertEqual(start_date.weekday(), WeekDays.Friday)
            self.assertEqual(end_date.weekday(), WeekDays.Monday)
            days_price = self.calc_price_for_days(start_date, (end_date - start_date).days)
            self.assertEqual(
                days_price,
                self.BASE_PRICE + self.WEEKEND_PRICE * 2,
                "Reservation is on Friday, Saturday, Sunday -> 1x base + 2x weekend prices",
            )

        with self.subTest("Weekdays only"):
            start_date = end_date
            end_date = start_date + timedelta(days=5)
            self.assertEqual(start_date.weekday(), WeekDays.Monday)
            self.assertEqual(end_date.weekday(), WeekDays.Saturday)
            days_price = self.calc_price_for_days(start_date, (end_date - start_date).days)
            self.assertEqual(
                days_price,
                self.BASE_PRICE * 5,
                "Reservation is from Monday to Friday -> 5x base prices",
            )

        with self.subTest("Weekend days only"):
            start_date = end_date
            end_date = start_date + timedelta(days=2)
            self.assertEqual(start_date.weekday(), WeekDays.Saturday)
            self.assertEqual(end_date.weekday(), WeekDays.Monday)
            days_price = self.calc_price_for_days(start_date, (end_date - start_date).days)
            self.assertEqual(
                days_price,
                self.WEEKEND_PRICE * 2,
                "Reservation is from Saturday to Sunday -> 5x weekend prices",
            )

    def test_visit_price_with_monthly_weekly_weekend_base_prices(self):
        reservation_length = self.MONTH_DAYS + 7 + 3

        end_date = date.today()
        end_date += timedelta(days=7 - end_date.weekday())  # we want end_date on Monday
        start_date = end_date - timedelta(days=reservation_length)

        models.Rate.objects.create(
            monthly=self.MONTHLY_PRICE,
            weekly=self.WEEKLY_PRICE,
            nightly=self.BASE_PRICE,
            weekend=self.WEEKEND_PRICE,
            time_frame=(start_date, end_date),
            prop=self.prop,
        )
        price = models.Rate.visit_price(
            start_date=start_date,
            end_date=end_date,
            prop_id=self.prop.pk,
            month_days=self.MONTH_DAYS,
        )
        last_three_days = start_date + timedelta(days=(self.MONTH_DAYS + 7))
        days_price = self.calc_price_for_days(last_three_days, 3)
        self.assertEqual(price, self.MONTHLY_PRICE + self.WEEKLY_PRICE + days_price)

    def test_visit_price_weekend_base_prices(self):
        start_date = date.today()
        # creates period from saturday to friday
        while start_date.weekday() != 5:
            start_date = start_date + timedelta(days=1)
        end_date = start_date + timedelta(days=6)
        models.Rate.objects.create(
            monthly=self.MONTHLY_PRICE,
            weekly=self.WEEKLY_PRICE,
            nightly=self.BASE_PRICE,
            weekend=self.WEEKEND_PRICE,
            time_frame=(start_date, end_date),
            prop=self.prop,
        )
        price = models.Rate.visit_price(
            start_date=start_date,
            end_date=end_date,
            prop_id=self.prop.pk,
            month_days=self.MONTH_DAYS,
        )
        self.assertEquals(price, self.WEEKEND_PRICE * 2 + self.BASE_PRICE * 4)

    def test_visit_price_single_rate(self):
        start_date = date.today()
        end_date = start_date + timedelta(days=10)

        rate = models.Rate.objects.create(
            nightly=self.BASE_PRICE, time_frame=(start_date, end_date), prop=self.prop
        )
        price = models.Rate.visit_price(
            start_date=start_date,
            end_date=end_date,
            prop_id=self.prop.pk,
            month_days=self.MONTH_DAYS,
        )
        self.assertEqual(price, (end_date - start_date).days * rate.nightly)

    def test_visit_price_multiple_rates(self):
        start_date = date.today()
        end_date = start_date + timedelta(days=10)
        rate1_from = start_date
        rate1_value = self.BASE_PRICE
        rate2_from = start_date + timedelta(days=5)
        rate2_value = self.BASE_PRICE * 2

        models.Rate.objects.create(
            nightly=rate1_value, time_frame=(rate1_from, rate2_from), prop=self.prop
        )
        models.Rate.objects.create(
            nightly=rate2_value, time_frame=(rate2_from, end_date), prop=self.prop
        )
        price = models.Rate.visit_price(
            start_date=start_date,
            end_date=end_date,
            prop_id=self.prop.pk,
            month_days=self.MONTH_DAYS,
        )

        rate2_days = (end_date - rate2_from).days
        rate1_days = (end_date - rate1_from).days - rate2_days
        correct_price = rate1_days * rate1_value + rate2_days * rate2_value
        self.assertEqual(price, correct_price)

    def test_visit_price_with_month_and_weeks_multiple_rates(self):
        rate1_days = 20
        start_date = date.today()
        end_date = start_date + timedelta(days=40)
        rate2_from = start_date + timedelta(days=rate1_days)

        rate1 = models.Rate.objects.create(
            monthly=self.MONTHLY_PRICE,
            weekly=self.WEEKLY_PRICE,
            nightly=self.BASE_PRICE,
            time_frame=(start_date, rate2_from),
            prop=self.prop,
        )
        rate2 = models.Rate.objects.create(
            monthly=self.MONTHLY_PRICE * 2,
            weekly=self.WEEKLY_PRICE * 2,
            nightly=self.BASE_PRICE * 2,
            time_frame=(rate2_from, end_date),
            prop=self.prop,
        )
        price = models.Rate.visit_price(
            start_date=start_date,
            end_date=end_date,
            prop_id=self.prop.pk,
            month_days=self.MONTH_DAYS,
        )

        rate2_days = self.MONTH_DAYS - rate1_days
        monthly_per_day_1 = rate1.monthly / self.MONTH_DAYS
        monthly_per_day_2 = rate2.monthly / self.MONTH_DAYS
        correct_price = (
            rate1_days * monthly_per_day_1
            + rate2_days * monthly_per_day_2
            + rate2.weekly
            + 3 * rate2.nightly
        )
        self.assertEqual(rate1_days + rate2_days + 7 + 3, (end_date - start_date).days)
        self.assertEqual(price, correct_price)

    def test_visit_price_multiple_rates_with_seasonal(self):
        start_date = date.today()
        end_date = start_date + timedelta(days=10)

        # Base Price
        base_pricing = models.PricingSettings.objects.create(
            nightly=self.BASE_PRICE, prop=self.prop
        )
        # Seasonal Rate
        seasonal_rate = models.Rate.objects.create(
            nightly=self.BASE_PRICE * 20,
            time_frame=DateRange(start_date + timedelta(days=2), end_date),
            seasonal=True,
            prop=self.prop,
        )
        # Custom Rate
        custom_rate = models.Rate.objects.create(
            nightly=self.BASE_PRICE * 10,
            time_frame=DateRange(start_date + timedelta(days=5), end_date),
            prop=self.prop,
        )

        # CustomRate overwrites SeasonalRate, SeasonalRate overwrites PricingSettings
        custom_duration = (end_date - custom_rate.time_frame.lower).days
        seasonal_duration = (end_date - seasonal_rate.time_frame.lower).days - custom_duration
        base_duration = (end_date - start_date).days - seasonal_duration - custom_duration

        correct_price = (
            custom_duration * custom_rate.nightly
            + seasonal_duration * seasonal_rate.nightly
            + base_duration * base_pricing.nightly
        )

        price = models.Rate.visit_price(
            start_date=start_date,
            end_date=end_date,
            prop_id=self.prop.pk,
            month_days=self.MONTH_DAYS,
        )

        self.assertEqual(price, correct_price)
        self.prop.pricing_settings.delete()

    def test_visit_price_missing_rate(self):
        start_date = date.today()
        end_date = start_date + timedelta(days=10)

        models.Rate.objects.create(
            nightly=self.BASE_PRICE,
            time_frame=(start_date + timedelta(days=5), end_date),
            prop=self.prop,
        )
        with self.assertRaises(ValueError):
            models.Rate.visit_price(
                start_date=start_date,
                end_date=end_date,
                prop_id=self.prop.pk,
                month_days=self.MONTH_DAYS,
            )

    def test_visit_price_unbounded_rate(self):
        today = date.today()

        models.Rate.objects.bulk_create(
            (
                models.Rate(nightly=self.BASE_PRICE, time_frame=(None, today), prop=self.prop),
                models.Rate(nightly=self.BASE_PRICE, time_frame=(today, None), prop=self.prop),
            )
        )

        with self.subTest(msg="Lower date is unbound"):
            stay_days = 2
            value = models.Rate.visit_price(
                start_date=today - timedelta(days=stay_days),
                end_date=today,
                prop_id=self.prop.pk,
                month_days=self.MONTH_DAYS,
            )
            self.assertEqual(value, self.BASE_PRICE * stay_days)

        with self.subTest(msg="Upper date is unbound"):
            stay_days = 2
            value = models.Rate.visit_price(
                start_date=today,
                end_date=today + timedelta(days=stay_days),
                prop_id=self.prop.pk,
                month_days=self.MONTH_DAYS,
            )
            self.assertEqual(value, self.BASE_PRICE * stay_days)


class ReservationRateTest(TestCase):
    def test_value(self):
        res_rate_value = models.ReservationRate._meta.get_field("value")
        rate_value = models.Rate._meta.get_field("nightly")
        self.assertEqual(res_rate_value.decimal_places, rate_value.decimal_places)
        self.assertEqual(res_rate_value.max_digits, rate_value.max_digits)


class ReservationTestCase(TestCase):

    TOTAL_RATE = Decimal("1000")

    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create()
        cls.prop = models.Property.objects.create(
            name="Name",
            property_type=models.Property.Types.Apartment.value,
            rental_type=models.Property.Rentals.Private.value,
            organization=cls.org,
        )
        PlanSettings.objects.create(team=1, properties=10, organization=cls.prop.organization)
        models.PricingSettings.objects.create(nightly=Decimal("200"), prop=cls.prop)
        today = date.today()
        cls.guest = Contact.objects.create(
            first_name="Test", last_name="test", organization=cls.org
        )
        cls.reservation = models.Reservation.objects.create(
            start_date=today,
            end_date=today + timedelta(days=10),
            price=Decimal("0"),
            paid=Decimal("0.00"),
            prop=cls.prop,
            guests_adults=1,
            guest=cls.guest,
        )

    def setUp(self):
        models.AdditionalFee.objects.all().delete()
        models.Discount.objects.all().delete()

    @mock.patch("listings.models.Rate.visit_price", return_value=TOTAL_RATE)
    def test_calculate_price_commit(self, m_visit_price):
        self.reservation.calculate_price(commit=True)
        self.assertEqual(self.reservation.price, self.TOTAL_RATE)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.price, self.TOTAL_RATE)

    def test_calculate_price_fail(self):
        with self.subTest(msg="Ends before starts"):
            reservation = models.Reservation(
                start_date=self.reservation.start_date,
                end_date=self.reservation.start_date - timedelta(days=1),
            )
            with self.assertRaises(ValueError):
                reservation.calculate_price()

        with self.subTest(msg="Ends when starts"):
            reservation = models.Reservation(
                start_date=self.reservation.start_date,
                end_date=self.reservation.start_date - timedelta(days=1),
            )
            with self.assertRaises(ValueError):
                reservation.calculate_price()

        with self.subTest(msg="Missing rate"), (
            mock.patch("listings.models.Rate.visit_price", side_effect=ValueError)
        ) as m_visit_price:
            with self.assertRaises(ValueError):
                self.reservation.calculate_price()
            m_visit_price.assert_called_once()

        with self.subTest(msg="Missing end date"), self.assertRaises(ValueError):
            reservation = models.Reservation(start_date=self.reservation.start_date, end_date=None)
            reservation.calculate_price()

    @mock.patch("listings.models.Rate.visit_price", return_value=TOTAL_RATE)
    def test_calculate_price_no_discounts_fees(self, m_visit_price):
        self.reservation.calculate_price()
        self.assertEqual(self.reservation.price, self.TOTAL_RATE)

    @mock.patch("listings.models.Rate.visit_price", return_value=TOTAL_RATE)
    def test_calculate_price_discount_huge(self, m_visit_price):
        models.Discount.objects.create(
            value=self.TOTAL_RATE * 100,
            prop=self.prop,
            days_before=10,
            discount_type=models.Discount.Types.Early_Bird.value,
        )
        self.reservation.calculate_price()
        self.assertEqual(self.reservation.price, 0)

    @mock.patch("listings.models.Rate.visit_price", return_value=TOTAL_RATE)
    def test_calculate_price_discounts(self, m_visit_price):
        per_stay_percent = [Decimal(i * 4) for i in range(1, 4)]
        per_day_percent = [Decimal(i * 3) for i in range(1, 4)]
        per_stay_fixed = [Decimal(i * 2) for i in range(1, 4)]
        per_day_fixed = [Decimal(i * 1) for i in range(1, 4)]

        models.Discount.objects.bulk_create(
            models.Discount(
                value=value,
                prop=self.prop,
                is_percentage=False,
                days_before=10,
                discount_type=models.Discount.Types.Late_Bird.value,
                calculation_method=CalculationMethod.Per_Stay.value,
            )
            for value in per_stay_fixed
        )
        models.Discount.objects.bulk_create(
            models.Discount(
                value=value,
                prop=self.prop,
                is_percentage=False,
                days_before=10,
                discount_type=models.Discount.Types.Late_Bird.value,
                calculation_method=CalculationMethod.Daily.value,
            )
            for value in per_day_fixed
        )
        models.Discount.objects.bulk_create(
            models.Discount(
                value=value,
                prop=self.prop,
                is_percentage=True,
                days_before=10,
                discount_type=models.Discount.Types.Late_Bird.value,
                calculation_method=CalculationMethod.Per_Stay.value,
            )
            for value in per_stay_percent
        )
        models.Discount.objects.bulk_create(
            models.Discount(
                value=value,
                prop=self.prop,
                is_percentage=True,
                days_before=10,
                discount_type=models.Discount.Types.Late_Bird.value,
                calculation_method=CalculationMethod.Daily.value,
            )
            for value in per_day_percent
        )

        visit_days = (self.reservation.end_date - self.reservation.start_date).days

        total_discount = sum(per_stay_fixed) + sum(per_day_fixed) * visit_days
        total_discount += self.TOTAL_RATE * sum(per_stay_percent) / Decimal("100")
        total_discount += self.TOTAL_RATE * sum(per_day_percent) / Decimal("100")

        self.assertLess(total_discount, self.TOTAL_RATE)
        self.reservation.calculate_price()
        self.assertEqual(self.reservation.price, self.TOTAL_RATE - total_discount)

    @mock.patch("listings.models.Rate.visit_price", return_value=TOTAL_RATE)
    def test_calculate_price_fees(self, m_visit_price):
        # assumption there are no Tax Fees

        stay_fees = [Decimal(i * 10) for i in range(1, 5)]
        daily_fees = [Decimal(i) for i in range(1, 5)]

        person_day_fees = [Decimal(i) for i in range(1, 5)]
        person_stay_fees = [Decimal(i) for i in range(1, 5)]

        stay_percent_fees = [Decimal(i) for i in range(1, 5)]
        stay_only_rates_percent_fees = [Decimal(i) for i in range(1, 5)]
        stay_no_taxes_percent = [Decimal(i) for i in range(1, 5)]

        models.AdditionalFee.objects.bulk_create(
            models.AdditionalFee(
                value=value,
                optional=False,
                calculation_method=CalculationMethod.Per_Stay.value,
                prop=self.prop,
            )
            for value in stay_fees
        )

        models.AdditionalFee.objects.bulk_create(
            models.AdditionalFee(
                value=value,
                optional=False,
                calculation_method=CalculationMethod.Daily.value,
                prop=self.prop,
            )
            for value in daily_fees
        )

        models.AdditionalFee.objects.bulk_create(
            models.AdditionalFee(
                value=value,
                optional=False,
                calculation_method=CalculationMethod.Per_Person_Per_Day.value,
                prop=self.prop,
            )
            for value in person_day_fees
        )

        models.AdditionalFee.objects.bulk_create(
            models.AdditionalFee(
                value=value,
                optional=False,
                calculation_method=CalculationMethod.Per_Person_Per_Stay.value,
                prop=self.prop,
            )
            for value in person_stay_fees
        )

        models.AdditionalFee.objects.bulk_create(
            models.AdditionalFee(
                value=value,
                optional=False,
                calculation_method=CalculationMethod.Per_Stay_Percent.value,
                prop=self.prop,
            )
            for value in stay_percent_fees
        )

        models.AdditionalFee.objects.bulk_create(
            models.AdditionalFee(
                value=value,
                optional=False,
                calculation_method=CalculationMethod.Per_Stay_Only_Rates_Percent.value,
                prop=self.prop,
            )
            for value in stay_only_rates_percent_fees
        )

        models.AdditionalFee.objects.bulk_create(
            models.AdditionalFee(
                value=value,
                optional=False,
                calculation_method=CalculationMethod.Per_Stay_No_Taxes_Percent.value,
                prop=self.prop,
            )
            for value in stay_no_taxes_percent
        )

        visit_days = (self.reservation.end_date - self.reservation.start_date).days
        guests = self.reservation.guests_adults + self.reservation.guests_children

        simple_fees = sum(stay_fees) + (sum(daily_fees) * visit_days)

        per_person_fees = (sum(person_day_fees) * guests * visit_days) + (
            sum(person_stay_fees) * guests
        )

        percent_only_rates = sum(stay_only_rates_percent_fees) / 100 * self.TOTAL_RATE

        stay_no_taxes_percent = (
            sum(stay_no_taxes_percent) / 100 * (simple_fees + per_person_fees + self.TOTAL_RATE)
        )

        stay_percent = (
            sum(stay_percent_fees) / 100 * (simple_fees + per_person_fees + self.TOTAL_RATE)
        )

        total_price = (
            simple_fees
            + per_person_fees
            + stay_percent
            + percent_only_rates
            + stay_no_taxes_percent
        )

        self.reservation.calculate_price()
        self.assertEqual(self.reservation.price, total_price + self.TOTAL_RATE)

    def test_active_cancellation_policy(self):
        policy = CancellationPolicy.Flexible

        self.reservation.cancellation_policy = policy
        self.reservation.save()
        self.assertEqual(self.reservation.active_cancellation_policy, policy.pretty_name)

        policy = CancellationPolicy.Long_Term
        self.reservation.cancellation_policy = CancellationPolicy.Unknown
        self.reservation.save()
        self.prop.organization.plansettings.cancellation_policy = policy
        self.prop.organization.plansettings.save()
        self.assertEqual(self.reservation.active_cancellation_policy, policy.pretty_name)

        policy = CancellationPolicy.Unknown
        self.prop.organization.plansettings.delete()
        self.prop.organization.refresh_from_db()
        self.assertEqual(self.reservation.active_cancellation_policy, policy.pretty_name)

    def test_dynamic_statuses(self):
        now = timezone.now()
        statuses = models.Reservation.Statuses
        dynamic_statuses = models.Reservation.DynamicStatuses
        start = now + timedelta(days=10)
        end = start + timedelta(days=10)
        expiration = now + timedelta(days=7)

        reservation = models.Reservation(
            start_date=start,
            end_date=end,
            paid=Decimal("0.00"),
            expiration=expiration,
            status=statuses.Inquiry.value,
        )
        with self.subTest(msg="Status Inquiry"):
            self.assertEqual(reservation.dynamic_status, dynamic_statuses.Inquiry.name)
        with self.subTest(msg="Status Pending"):
            reservation.status = statuses.Inquiry_Blocked.value
            self.assertEqual(reservation.dynamic_status, dynamic_statuses.Pending.name)
        with self.subTest(msg="Status Request"):
            reservation.status = statuses.Request.value
            self.assertEqual(reservation.dynamic_status, dynamic_statuses.Request.name)
        with self.subTest(msg="Status Expired Inquiry"):
            reservation.status = statuses.Inquiry.value
            reservation.expiration = now - timedelta(days=1)
            self.assertEqual(reservation.dynamic_status, dynamic_statuses.Expired.name)
        with self.subTest(msg="Status Expired Inquiry Blocked"):
            reservation.status = statuses.Inquiry_Blocked.value
            reservation.expiration = now - timedelta(days=1)
            self.assertEqual(reservation.dynamic_status, dynamic_statuses.Expired.name)
        with self.subTest(msg="Status Reserved"):
            reservation.status = statuses.Accepted.value
            self.assertEqual(reservation.dynamic_status, dynamic_statuses.Reserved.name)
        with self.subTest(msg="Status Canceled"):
            reservation.status = statuses.Cancelled.value
            self.assertEqual(reservation.dynamic_status, dynamic_statuses.Cancelled.name)
        with self.subTest(msg="Invalid status"):
            reservation.status = 100
            with self.assertRaises(ValueError):
                reservation.dynamic_status

    def test_init(self):
        reservation = models.Reservation.objects.only("id").get(id=self.reservation.id)
        self.assertIsInstance(reservation._initial_data, dict)


class Azure404Storage(AzureStorage):
    """Always return empty file, simulating resource was not found on Azure"""

    def _open(self, *args, **kwargs):
        return ContentFile("")


class ImageTest(TestCase):
    @override_settings(
        DEFAULT_FILE_STORAGE=".".join((Azure404Storage.__module__, Azure404Storage.__qualname__))
    )
    def test_dimension_when_missing_resource(self):
        image = models.Image.objects.create(
            url="non-existing/image.jpg", prop=models.Property.objects.create()
        )
        self.assertIsNone(image.url.width)
        self.assertIsNone(image.url.height)

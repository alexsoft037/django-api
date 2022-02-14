from collections import namedtuple
from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.dateparse import parse_datetime
from plaid.errors import PlaidError
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory
from stripe.error import InvalidRequestError

from accounts.models import Membership, Organization, Token
from crm.models import Contact
from payments import serializers
from payments.models import Charge, Coupon, Customer
from payments.services import Plaid
from payments.views import CouponViewSet


def side_effect(coupon_id):
    if coupon_id == "fail":
        raise InvalidRequestError(
            message="No such coupon",
            param="fail",
            json_body={"error": {"message": "No such coupon"}},
        )


# class SubscribeSerializerTestCase(TestCase):
#     serializer_class = serializers.SubscribeSerializer
#
#     @classmethod
#     def setUpTestData(cls):
#         cls.customer_external_id = "cust01"
#         cls.organization = Organization.objects.create(name="test_organization")
#         cls.customer = Customer.objects.create(
#             external_id=cls.customer_external_id, organization=cls.organization
#         )
#         cls.tier = ProductTier.objects.create(name="tier", external_id="tier")
#         # Commented out in case we come back to this. Currently using Stripe as source
#         # cls.pricing_plan = PricingPlan.objects.create(
#         #     alias="plan", amount=Decimal("10"), external_id="plan", tier=cls.tier
#         # )
#         cls.pricing_plan = PlanType.base.name
#         cls.Coupon = namedtuple("Coupon", ["valid"])
#
#     @mock.patch("payments.services.Stripe.retrieve_coupon", side_effect=side_effect)
#     def test_create_with_not_exist_coupon_id(self, m_retrieve_coupon):
#         s = self.serializer_class(
#             data={"plan": self.pricing_plan, "coupon_id": "fail"},
#             context={"organization": self.organization},
#         )
#         with self.assertRaises(ValidationError):
#             s.is_valid(raise_exception=True)
#         self.assertEqual(list(s.errors.keys()), ["coupon_id"])
#
#     @mock.patch("payments.services.Stripe.retrieve_coupon")
#     @mock.patch("payments.services.Stripe.subscribe")
#     def test_create_with_valid_coupon_id(self, m_subscribe, m_retrieve_coupon):
#         m_retrieve_coupon.return_value = self.Coupon(valid=True)
#         Subscript = namedtuple("Subscript", ["id"])
#         m_subscribe.return_value = Subscript(id="123")
#         s = self.serializer_class(
#             data={"plan": self.pricing_plan, "coupon_id": "valid"},
#             context={"organization": self.organization},
#         )
#         self.assertTrue(s.is_valid())
#         s.save()
#         queryset = Subscription.objects.filter(coupon_external_id="valid")
#         self.assertEquals(queryset.count(), 1)
#         subscription = queryset.first()
#         self.assertEquals(subscription.external_id, "123")
#
#     @mock.patch("payments.services.Stripe.retrieve_coupon")
#     def test_create_with_invalid_coupon_id(self, m_retrieve_coupon):
#         m_retrieve_coupon.return_value = self.Coupon(valid=False)
#         s = self.serializer_class(
#             data={"plan": self.pricing_plan, "coupon_id": "invalid"},
#             context={"organization": self.organization},
#         )
#         self.assertFalse(s.is_valid())
#
#     @mock.patch("payments.services.Stripe.subscribe")
#     @mock.patch("payments.services.Stripe.retrieve_coupon")
#     def test_subscription_create_with_coupon(self, m_retrieve_coupon, m_subscribe):
#         Subscribe = namedtuple("Subscribe", ["id"])
#         m_retrieve_coupon.return_value = self.Coupon(valid=True)
#         m_subscribe.return_value = Subscribe(id="1234")
#         s = self.serializer_class(
#             data={"plan": self.pricing_plan, "coupon_id": "valid"},
#             context={"organization": self.organization},
#         )
#         self.assertTrue(s.is_valid())
#         s.save()
#         self.assertEqual(Subscription.objects.all().count(), 1)
#         subscription = Subscription.objects.first()
#         self.assertEqual(subscription.external_id, "1234")
#         self.assertEquals(subscription.coupon_external_id, "valid")
#
#     @mock.patch("payments.services.Stripe.subscribe")
#     def test_subscription_create_without_coupon(self, m_subscribe):
#         Subscribe = namedtuple("Subscribe", ["id"])
#         m_subscribe.return_value = Subscribe(id="1234")
#         s = self.serializer_class(
#             data={"plan": self.pricing_plan}, context={"organization": self.organization}
#         )
#         self.assertTrue(s.is_valid())
#         s.save()
#         self.assertEqual(Subscription.objects.all().count(), 1)
#         subscription = Subscription.objects.first()
#         self.assertEqual(subscription.external_id, "1234")


class BaseCreditCardSerializerTest(TestCase):
    serializer_class = serializers.BaseCreditCardSerializer

    def test_get_data(self):
        card = mock.Mock(last4=1234, id=4321, brand="Visa", exp_year=2020, exp_month=12)
        serializer = self.serializer_class()
        data = serializer._get_data(card, "customer_id")
        self.assertIsInstance(data, dict)


class CreditCardSerializerTest(TestCase):
    serializer_class = serializers.CreditCardSerializer

    @mock.patch("payments.serializers.Stripe.add_card")
    def test_create(self, m_add_card):
        m_add_card.return_value = mock.Mock(
            last4=1234, id=4321, brand="Visa", exp_year=2020, exp_month=12
        )
        organization = Organization.objects.create()
        customer = Customer.objects.create(external_id="ext_id", organization=organization)
        serializer = self.serializer_class(
            data={"token": "tok_visa", "customer": customer.id},
            context={"organization": organization},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        instance = serializer.save()
        self.assertIsNotNone(instance.customer_obj)

        customer.refresh_from_db()
        self.assertTrue(customer.credit_cards.filter(id=instance.id).exists())


class GuestCreditCardSerializerTest(TestCase):
    serializer_class = serializers.GuestCreditCardSerializer

    @mock.patch("payments.serializers.Stripe.add_card")
    def test_create(self, m_add_card):
        m_add_card.return_value = mock.Mock(
            last4=1234, id=4321, brand="Visa", exp_year=2020, exp_month=12
        )
        organization = Organization.objects.create()
        customer = Contact.objects.create(external_id="ext_id", organization=organization)
        serializer = self.serializer_class(
            data={"token": "tok_visa", "customer": customer.id},
            context={"organization": organization},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        instance = serializer.save()
        self.assertIsNotNone(instance.customer_obj)

        customer.refresh_from_db()
        self.assertTrue(customer.credit_cards.filter(id=instance.id).exists())


class CouponSerializerTest(TestCase):
    serializer_class = serializers.CouponSerializer

    def test_is_valid_with_valid_inner_coupon_data(self):
        data = {
            "external_id": "F205",
            "name": "Name",
            "percent_off": "10.15",
            "duration": "repeating",
            "duration_in_months": "3",
            "max_redemptions": "3",
            "redeem_by": "2018-12-11 05:45Z",
            "is_valid": "True",
        }
        exp_data = {
            "external_id": "F205",
            "name": "Name",
            "percent_off": Decimal("10.15"),
            "duration": "repeating",
            "duration_in_months": 3,
            "max_redemptions": 3,
            "redeem_by": parse_datetime("2018-12-11 05:45Z"),
            "is_valid": True,
        }

        s = self.serializer_class(data=data)
        self.assertTrue(s.is_valid())
        self.assertDictEqual(exp_data, s.validated_data)

    def test_is_valid_with_valid_outer_coupon_data(self):
        data = {
            "id": "F205",
            "name": "Name",
            "amount_off": 10,
            "currency": "usd",
            "duration": "repeating",
            "duration_in_months": "3",
            "max_redemptions": "3",
            "redeem_by": 1_535_438_100,
            "valid": False,
        }
        exp_data = {
            "external_id": "F205",
            "name": "Name",
            "amount_off": 10,
            "currency": "USD",
            "duration": "repeating",
            "duration_in_months": 3,
            "max_redemptions": 3,
            "redeem_by": parse_datetime("2018-08-28 06:35Z"),
            "is_valid": False,
        }

        s = self.serializer_class(data=data)
        self.assertTrue(s.is_valid())
        self.assertDictEqual(exp_data, s.validated_data)

    def test_is_valid_with_passed_percent_off_and_amount_off(self):
        data = {
            "external_id": "F205",
            "name": "Name",
            "percent_off": 10,
            "amount_off": 10,
            "currency": "usd",
            "duration": "repeating",
            "duration_in_months": "3",
        }

        self.check_validation_errors(data, "Only one of percent_off, amount_off must be set")

    def test_is_valid_with_not_passed_percent_off_and_amount_off(self):
        data = {
            "external_id": "F205",
            "name": "Name",
            "currency": "usd",
            "duration": "repeating",
            "duration_in_months": "3",
        }

        self.check_validation_errors(data, "Only one of percent_off, amount_off must be set")

    def test_is_valid_with_percent_off_equals_zero(self):
        data = {
            "external_id": "F205",
            "name": "Name",
            "percent_off": "0",
            "currency": "usd",
            "duration": "repeating",
            "duration_in_months": "3",
        }

        self.check_validation_errors(data, "must be greater than 0")

    def test_is_valid_with_percent_off_less_zero(self):
        data = {
            "external_id": "F205",
            "name": "Name",
            "percent_off": "-1",
            "currency": "usd",
            "duration": "repeating",
            "duration_in_months": "3",
        }

        self.check_validation_errors(data, "must be greater than 0")

    def test_is_valid_with_amount_off_less_one(self):
        data = {
            "external_id": "F205",
            "name": "Name",
            "amount_off": "0",
            "currency": "usd",
            "duration": "repeating",
            "duration_in_months": "3",
        }

        self.check_validation_errors(data, "must be greater than 0")

    def test_is_valid_with_passed_duration_repeating_without_duration_in_months(self):
        data = {
            "external_id": "F205",
            "name": "Name",
            "amount_off": 1,
            "currency": "usd",
            "duration": "repeating",
        }

        self.check_validation_errors(data, "must be set when duration is repeating")

    def test_is_valid_with_passed_duration_repeating_with_duration_in_months_less_one(self):
        data = {
            "external_id": "F205",
            "name": "Name",
            "amount_off": "1",
            "currency": "usd",
            "duration": "repeating",
            "duration_in_months": "0",
        }

        self.check_validation_errors(data, "must be greater than 0")

    def test_is_valid_with_passed_duration_repeating_with_duration_in_months(self):
        data = {
            "external_id": "F205",
            "name": "Name",
            "amount_off": 1,
            "currency": "usd",
            "duration": "repeating",
            "duration_in_months": "3",
        }

        s = self.serializer_class(data=data)
        self.assertTrue(s.is_valid())

    def test_is_valid_with_passed_duration_not_repeating_without_duration_in_months(self):
        data = {
            "external_id": "F205",
            "name": "Name",
            "amount_off": 1,
            "currency": "usd",
            "duration": "once",
        }

        s = self.serializer_class(data=data)
        self.assertTrue(s.is_valid())

    def test_is_valid_with_max_redemptions_less_one(self):
        data = {
            "external_id": "F205",
            "name": "Name",
            "amount_off": "1",
            "currency": "usd",
            "duration": "repeating",
            "duration_in_months": "3",
            "max_redemptions": 0,
        }

        self.check_validation_errors(data, "must be greater than 0")

    def test_create_with_new_coupon(self):
        data = {
            "external_id": "F205",
            "name": "Name",
            "amount_off": 1,
            "currency": "USD",
            "duration": "repeating",
            "duration_in_months": 3,
        }
        Coupon.objects.create(**data)

        new_data = dict(data)
        new_data["external_id"] = "B201"
        s = self.serializer_class(data=new_data)
        self.assertTrue(s.is_valid())

        s.save()
        self.assertEqual(2, Coupon.objects.count())

    def test_create_with_old_coupon(self):
        data = {
            "external_id": "F205",
            "name": "Name",
            "amount_off": 1,
            "currency": "USD",
            "duration": "repeating",
            "duration_in_months": 3,
        }
        Coupon.objects.create(**data)

        new_data = dict(data)
        new_data["valid"] = False
        s = self.serializer_class(data=new_data)
        self.assertTrue(s.is_valid())

        s.save()
        self.assertEqual(1, Coupon.objects.count())

    def check_validation_errors(self, data, error_str):
        s = self.serializer_class(data=data)
        self.assertFalse(s.is_valid())

        errs = list(s.errors.values())
        self.assertEqual(1, len(errs))
        errs = errs[0]
        self.assertEqual(1, len(errs))
        self.assertTrue(error_str in errs)


class ChargeRefundSerializerTest(TestCase):
    def _get_charge(self):
        return Charge(
            external_id="ext_charge", amount=10, refunded_amount=0, status=Charge.Status.Succeeded
        )

    @mock.patch("payments.serializers.Stripe.refund")
    def test_validate_to_refund(self, m_refund):
        to_refund = self._get_charge().amount - 1

        with self.subTest("Unknown charge"):
            m_refund.reset_mock()
            serializer = serializers.ChargeRefundSerializer(instance=None)
            with self.assertRaises(ValidationError):
                serializer.validate_to_refund(to_refund)
            m_refund.assert_not_called()

        with self.subTest("Not refundable charge"):
            m_refund.reset_mock()
            charge = self._get_charge()
            charge.is_refundable = False

            serializer = serializers.ChargeRefundSerializer(instance=charge)
            self.assertEqual(
                serializer.validate_to_refund(to_refund),
                to_refund,
                "'is_refundable' is a mark for guest, owner can refund any charge",
            )
            m_refund.assert_called_once()

        with self.subTest("Trying to refund too much"):
            m_refund.reset_mock()
            charge = self._get_charge()
            charge.refunded_amount = charge.amount

            serializer = serializers.ChargeRefundSerializer(instance=charge)
            with self.assertRaises(ValidationError):
                serializer.validate_to_refund(to_refund)
            m_refund.assert_not_called()

        with self.subTest("Only able to refund succeeded charge"):
            m_refund.reset_mock()
            charge = self._get_charge()
            for charge_status in (
                Charge.Status.Delayed,
                Charge.Status.Failed,
                Charge.Status.Pending,
            ):
                charge.status = charge_status
                serializer = serializers.ChargeRefundSerializer(instance=charge)
                with self.assertRaises(ValidationError):
                    serializer.validate_to_refund(to_refund)
            m_refund.assert_not_called()

            charge.status = Charge.Status.Succeeded
            self.assertEqual(serializer.validate_to_refund(to_refund), to_refund)
            m_refund.assert_called_once()


class CouponViewSetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.factory = APIRequestFactory()
        User = get_user_model()
        cls.user = User.objects.create(
            username="test",
            first_name="some first name",
            last_name="some last name",
            is_superuser=True,
        )
        Membership.objects.create(
            organization=Organization.objects.create(), user=cls.user, is_default=True
        )
        cls.token = Token.objects.create(
            name="user_token", user=cls.user, organization=cls.user.organization
        )

    @property
    def coupon_data(self):
        return {
            "external_id": "F205",
            "name": "Name",
            "amount_off": 1,
            "currency": "USD",
            "duration": "repeating",
            "duration_in_months": 3,
        }

    @mock.patch("payments.services.Stripe.create_coupon")
    def test_create_with_success_stripe_create_coupon(self, m_create_coupon):
        request = self.factory.post(
            "/", data=self.coupon_data, HTTP_AUTHORIZATION=f"Token: {self.token.generate_key()}"
        )
        # force_authenticate(request, user=user)
        view = CouponViewSet.as_view({"post": "create"})
        response = view(request)
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        self.assertEqual(1, Coupon.objects.count())

    @mock.patch(
        "payments.services.Stripe.create_coupon",
        side_effect=InvalidRequestError(
            "mess", "F205", json_body={"error": {"message": "very bad"}}
        ),
    )
    def test_create_with_stripe_bad_request_error(self, m_create_coupon):
        request = self.factory.post(
            "/", data=self.coupon_data, HTTP_AUTHORIZATION=f"Token: {self.token.generate_key()}"
        )
        view = CouponViewSet.as_view({"post": "create"})
        response = view(request)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertEqual(0, Coupon.objects.count())

    @mock.patch("payments.services.Stripe.create_coupon", side_effect=Exception)
    def test_create_with_stripe_exception(self, m_create_coupon):
        request = self.factory.post(
            "/", data=self.coupon_data, HTTP_AUTHORIZATION=f"Token: {self.token.generate_key()}"
        )
        view = CouponViewSet.as_view({"post": "create"})
        response = view(request)
        self.assertEqual(status.HTTP_500_INTERNAL_SERVER_ERROR, response.status_code)
        self.assertEqual(0, Coupon.objects.count())

    @mock.patch("payments.services.Stripe.delete_coupon")
    def test_destroy_with_success_stripe_delete_coupon(self, m_delete_coupon):
        c = Coupon.objects.create(**self.coupon_data)
        self.assertEqual(1, Coupon.objects.count())
        request = self.factory.delete(
            "/", HTTP_AUTHORIZATION=f"Token: {self.token.generate_key()}"
        )
        view = CouponViewSet.as_view({"delete": "destroy"})
        response = view(request, pk=c.id)
        self.assertEqual(status.HTTP_204_NO_CONTENT, response.status_code)
        self.assertEqual(0, Coupon.objects.count())

    @mock.patch(
        "payments.services.Stripe.delete_coupon",
        side_effect=InvalidRequestError("message", "F205", "resource_missing"),
    )
    def test_destroy_with_stripe_coupon_not_found(self, m_delete_coupon):
        c = Coupon.objects.create(**self.coupon_data)
        request = self.factory.delete(
            "/", HTTP_AUTHORIZATION=f"Token: {self.token.generate_key()}"
        )
        view = CouponViewSet.as_view({"delete": "destroy"})
        response = view(request, pk=c.id)
        self.assertEqual(status.HTTP_204_NO_CONTENT, response.status_code)
        self.assertEqual(0, Coupon.objects.count())

    @mock.patch(
        "payments.services.Stripe.delete_coupon", side_effect=InvalidRequestError("mess", "F205")
    )
    def test_destroy_with_stripe_coupon_bad_request_error(self, m_delete_coupon):
        coupon = Coupon.objects.create(**self.coupon_data)
        request = self.factory.delete(
            "/", HTTP_AUTHORIZATION=f"Token: {self.token.generate_key()}"
        )
        view = CouponViewSet.as_view({"delete": "destroy"})
        response = view(request, pk=coupon.id)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertEqual(1, Coupon.objects.count())

    @mock.patch("payments.services.Stripe.delete_coupon", side_effect=Exception)
    def test_destroy_with_stripe_coupon_error(self, m_delete_coupon):
        c = Coupon.objects.create(**self.coupon_data)
        request = self.factory.delete(
            "/", HTTP_AUTHORIZATION=f"Token: {self.token.generate_key()}"
        )
        view = CouponViewSet.as_view({"delete": "destroy"})
        response = view(request, pk=c.id)
        self.assertEqual(status.HTTP_500_INTERNAL_SERVER_ERROR, response.status_code)
        self.assertEqual(1, Coupon.objects.count())

    @mock.patch("payments.services.Stripe.retrieve_coupon", autospec=True)
    def test_sync_ok(self, m_retrieve_coupon):
        # mock for stripe coupon
        class StripeCoupon(
            namedtuple(
                "Coupon",
                [
                    "id",
                    "name",
                    "amount_off",
                    "currency",
                    "duration",
                    "duration_in_months",
                    "valid",
                ],
            )
        ):
            def to_dict(self):
                return self._asdict()

        m_retrieve_coupon.return_value = StripeCoupon(
            id="F205",
            name="Name",
            amount_off=1,
            currency="usd",
            duration="repeating",
            duration_in_months=3,
            valid=False,
        )
        c = Coupon.objects.create(**self.coupon_data)
        request = self.factory.post("/", HTTP_AUTHORIZATION=f"Token: {self.token.generate_key()}")
        view = CouponViewSet.as_view({"post": "sync"})
        response = view(request, pk=c.id)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(1, Coupon.objects.count())
        self.assertEqual(False, Coupon.objects.all().first().is_valid)

    @mock.patch("payments.services.Stripe.retrieve_coupon")
    def test_sync_coupon_not_found(self, m_delete_coupon):
        request = self.factory.post("/", HTTP_AUTHORIZATION=f"Token: {self.token.generate_key()}")
        view = CouponViewSet.as_view({"post": "sync"})
        response = view(request, pk=0)
        self.assertEqual(status.HTTP_404_NOT_FOUND, response.status_code)

    @mock.patch(
        "payments.services.Stripe.retrieve_coupon",
        side_effect=InvalidRequestError("message", "F205", "resource_missing"),
    )
    def test_sync_stripe_retrieve_coupon_not_found(self, m_retrieve_coupon):
        c = Coupon.objects.create(**self.coupon_data)
        request = self.factory.post("/", HTTP_AUTHORIZATION=f"Token: {self.token.generate_key()}")
        view = CouponViewSet.as_view({"post": "sync"})
        response = view(request, pk=c.id)
        self.assertEqual(status.HTTP_204_NO_CONTENT, response.status_code)
        self.assertEqual(0, Coupon.objects.count())

    @mock.patch(
        "payments.services.Stripe.retrieve_coupon", side_effect=InvalidRequestError("mess", "F205")
    )
    def test_sync_stripe_retrieve_coupon_bad_request(self, m_retrieve_coupon):
        c = Coupon.objects.create(**self.coupon_data)
        request = self.factory.post("/", HTTP_AUTHORIZATION=f"Token: {self.token.generate_key()}")
        view = CouponViewSet.as_view({"post": "sync"})
        response = view(request, pk=c.id)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertEqual(1, Coupon.objects.count())

    @mock.patch("payments.services.Stripe.retrieve_coupon", side_effect=Exception)
    def test_sync_stripe_retrieve_coupon_exception(self, m_retrieve_coupon):
        c = Coupon.objects.create(**self.coupon_data)
        request = self.factory.post("/", HTTP_AUTHORIZATION=f"Token: {self.token.generate_key()}")
        view = CouponViewSet.as_view({"post": "sync"})
        response = view(request, pk=c.id)
        self.assertEqual(status.HTTP_500_INTERNAL_SERVER_ERROR, response.status_code)
        self.assertEqual(1, Coupon.objects.count())


class PlaidSerializerTest(TestCase):
    serializer_class = serializers.PlaidSerializer

    @mock.patch("payments.serializers.Plaid.exchange")
    def test_validate(self, m_exchange):
        context = {"organization": Organization.objects.create(name="test_organization")}

        public_token = "user-public-token"
        success_exchenge = {"item_id": "SomeRandomId", "access_token": "private-access-token"}
        failure_exchange = {"error": {"type": "Some type", "message": "Whoopsie"}}

        with self.subTest("Valid public_token"):
            m_exchange.return_value = success_exchenge
            serializer = self.serializer_class(
                data={"public_token": public_token}, context=context
            )
            self.assertTrue(serializer.is_valid(), serializer.errors)
            instance = serializer.save()
            self.assertEqual(instance.access_token, success_exchenge["access_token"])
            self.assertEqual(instance.item_id, success_exchenge["item_id"])

        with self.subTest("Invalid public_token"):
            m_exchange.return_value = failure_exchange
            serializer = self.serializer_class(
                data={"public_token": public_token}, context=context
            )
            self.assertFalse(serializer.is_valid())
            self.assertIn("public_token", serializer.errors)
            self.assertEqual(serializer.errors["public_token"], failure_exchange["error"])


class PlaidTest(TestCase):
    @mock.patch("payments.services.Plaid.client")
    def test_get_transactions(self, m_client):
        count = 10
        access_token = "access_token"
        start_date = end_date = date.today()

        with self.subTest("Valid responses"):
            m_client.Transactions.get.side_effect = [
                {"total_transactions": count * 2.5, "transactions": list(range(count))},
                {"total_transactions": count * 2.5, "transactions": list(range(count))},
                {"total_transactions": count * 2.5, "transactions": list(range(count // 2))},
            ]
            transactions = Plaid.get_transactions(access_token, start_date, end_date, count=count)
            self.assertIn("transactions", transactions)
            self.assertNotIn("error", transactions)

        with self.subTest("Invalid responses"):
            m_client.Transactions.get.side_effect = [
                {"total_transactions": count * 2.5, "transactions": list(range(count))},
                PlaidError("message", "type", "code", "display_message"),
                {"total_transactions": count * 2.5, "transactions": list(range(count))},
            ]
            transactions = Plaid.get_transactions(access_token, start_date, end_date, count=count)
            self.assertNotIn("transactions", transactions)
            self.assertIn("error", transactions)

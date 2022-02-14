from functools import partial, wraps
from itertools import chain
from logging import getLogger
from math import ceil

import plaid
import stripe
from django.conf import settings

logger = getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET

StripeError = stripe.error.StripeError


class Stripe:
    def subscribe(self, customer_id, plan_id, coupon_id=None, **kwargs):
        try:
            sub = stripe.Subscription.create(
                customer=customer_id,
                items=[{"plan": plan_id}],
                coupon=coupon_id,
                **kwargs
            )
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise
        return sub

    def update_subscription(self, subscription_id, **kwargs):
        try:
            sub = stripe.Subscription.modify(
                subscription_id,
                **kwargs
            )
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise
        return sub

    def unsubscribe(self, subscription_id):
        try:
            stripe.Subscription.delete(subscription_id)
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise

    def update_item_quantity(self, subscription_id, product_id, quantity):
        try:
            items = stripe.SubscriptionItem.list(subscription=subscription_id)
            item_id = None
            for i in items:
                if i.plan.product == product_id:
                    item_id = i.id
            sub = stripe.SubscriptionItem.modify(
                item_id,
                quantity=quantity
            )
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise

        return sub

    def add_card(self, customer_id, card_token):
        try:
            customer = stripe.Customer.retrieve(customer_id)
            cc = customer.sources.create(source=card_token)
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise

        return cc

    def modify_card(self, customer_id, card_token, card_details):
        try:
            cc = stripe.Customer.modify_source(
                customer_id, card_token, metadata=card_details)
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise
        return cc

    def remove_card(self, customer_id, card_token):
        try:
            customer = stripe.Customer.retrieve(customer_id)
            cc = customer.sources.retrieve(card_token)
            cc.delete()
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise

    def list_cards(self, customer_id):
        try:
            ccs = stripe.Customer.retrieve(customer_id).sources.list(limit=10, object="card")
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise
        return ccs["data"]

    def list_charges(self, customer_id, limit=10):
        try:
            ccs = stripe.Charge.list(customer=customer_id, limit=limit)
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise
        return ccs["data"]

    def list_invoices(self, customer_id, limit=10, **kwargs):
        try:
            invoices = stripe.Invoice.list(customer=customer_id, limit=limit, **kwargs)
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise
        return invoices["data"]

    def create_customer(self, **kwargs):
        try:
            customer = stripe.Customer.create(**kwargs)
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise
        return customer

    def charge(self, connect_account_id: str, amount: int, source_id: str, currency="usd"):
        try:
            charge = stripe.Charge.create(
                amount=amount,
                currency=currency.lower(),
                source=source_id,
                destination={"account": connect_account_id},
            )
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise
        return charge

    def refund(self, charge_id: str, amount: int = None):
        try:
            refund = stripe.Refund.create(charge=charge_id, amount=amount)
        except StripeError as e:
            logger.warn("StripeError : %s", e)
            raise
        return refund

    def list_disputes(self, query):
        try:
            disputes = stripe.Dispute.list(**query)
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise
        return disputes

    def list_after_disputes(self, after) -> list:
        def get_disputes(query):
            resp = self.list_disputes(query)
            disputes = resp.data
            if resp.has_more:
                last_id = resp.data[-1].id
                return disputes + get_disputes({"starting_after": last_id})
            return disputes

        return get_disputes({"starting_after": after} if after else {})

    def retrieve_dispute(self, dispute_id):
        try:
            dispute = stripe.Dispute.retrieve(dispute_id)
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise
        return dispute

    def update_dispute(self, dispute_id, evidence: dict):
        try:
            dispute = stripe.Dispute.retrieve(dispute_id)
            dispute.evidence = evidence
            dispute.save()
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise
        return dispute

    def close_dispute(self, dispute_id):
        try:
            dispute = stripe.Dispute.retrieve(dispute_id)
            dispute.close()
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise
        return dispute

    def retrieve_coupon(self, coupon_id):
        try:
            coupon = stripe.Coupon.retrieve(coupon_id)
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise
        return coupon

    def create_coupon(
        self,
        coupon_id,
        duration,
        duration_in_months=None,
        name=None,
        percent_off=None,
        amount_off=None,
        currency=None,
        max_redemptions=None,
        redeem_by=None,
    ):
        try:
            coupon = stripe.Coupon.create(
                id=coupon_id,
                name=name,
                duration=duration,
                duration_in_months=duration_in_months,
                percent_off=percent_off,
                amount_off=amount_off,
                currency=currency,
                max_redemptions=max_redemptions,
                redeem_by=redeem_by,
            )
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise
        return coupon

    def delete_coupon(self, coupon_id):
        try:
            coupon = stripe.Coupon.retrieve(coupon_id)
            coupon.delete()
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise
        return coupon

    def list_coupons(self, query):
        try:
            coupon = stripe.Coupon.list(**query)
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise
        return coupon

    def list_after_coupons(self, after=None) -> list:
        def get_coupons(query):
            resp = self.list_coupons(query)
            coupons = resp.data
            if resp.has_more:
                last_id = resp.data[-1].id
                return coupons + get_coupons({"starting_after": last_id})
            return coupons

        return get_coupons({"starting_after": after})

    def retrieve_subscription(self, sub_id):
        try:
            sub = stripe.Subscription.retrieve(sub_id)
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise
        return sub

    def retrieve_charge(self, charge_id):
        try:
            charge = stripe.Charge.retrieve(charge_id)
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise
        return charge

    def retrieve_charge_receipt_url(self, charge_id):
        charge = self.retrieve_charge(charge_id)
        return charge.receipt_url

    def retrieve_upcoming_invoice(self, subscription_id, **kwargs):
        try:
            invoice = stripe.Invoice.upcoming(subscription=subscription_id, **kwargs)
        except StripeError as e:
            logger.warning("StripeError : %s", e)
            raise
        return invoice


def _serializer_plaid_error(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            ret = fn(*args, **kwargs)
        except plaid.errors.PlaidError as e:
            ret = {"error": {"message": e.display_message, "type": e.type}}
        return ret

    return wrapper


class Plaid:
    client = plaid.Client(
        client_id=settings.PLAID_CLIENT_ID,
        secret=settings.PLAID_SECRET,
        public_key=settings.PLAID_PUBLIC_KEY,
        environment=settings.PLAID_ENV,
        api_version="2018-05-22",
    )

    @classmethod
    @_serializer_plaid_error
    def exchange(cls, public_token: str) -> dict:
        return cls.client.Item.public_token.exchange(public_token)

    @classmethod
    @_serializer_plaid_error
    def get_transactions(cls, access_token: str, start_date, end_date, count=150) -> dict:
        _get_transactions = partial(
            cls.client.Transactions.get,
            access_token,
            start_date.isoformat(),
            end_date.isoformat(),
            count=count,
        )
        response = _get_transactions(offset=0)
        transactions = response["transactions"]

        calls_to_make = ceil(response["total_transactions"] / count)
        transactions.extend(
            chain.from_iterable(
                _get_transactions(offset=count * i)["transactions"]
                for i in range(1, calls_to_make)
            )
        )

        return {"transactions": transactions}

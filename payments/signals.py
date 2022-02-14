from django.conf import settings
from django.db.models import signals
from django.dispatch import receiver

from accounts.models import Organization
from accounts.signals import property_activated, subscription_started
from cozmo_common.functions import non_test_receiver
from listings.choices import PropertyStatuses
from listings.models import Property, Reservation
from listings.signals import reservation_changed
from payments.choices import PlanType
from payments.serializers import SubscribeSerializer
from payments.services import Stripe
from .models import Charge


@receiver(signals.post_save, sender=Charge)
def charge_saved(sender, created, instance, **kwargs):
    if not isinstance(instance.payment_for, Reservation):
        return

    event_changes = {}
    if created:
        event_changes["payment"] = str(instance.amount)
    else:
        changes = instance._changed_fields()
        if "refunded_amount" in changes:
            event_changes["refund"] = str(instance.refunded_amount - changes["refunded_amount"])

    reservation_changed.send(
        sender=Reservation, changes=event_changes, instance=instance.payment_for
    )


def _update_subscription_quantity(prop):
    org = prop.organization
    sub = org.subscription.first()
    stripe = Stripe()
    stripe.update_item_quantity(
        subscription_id=sub.external_id,
        product_id=settings.SUBSCRIPTION_PLANS["base"]["product_id"],
        quantity=org.property_set.filter(status=PropertyStatuses.Active).count(),
    )


@receiver(subscription_started, sender=Organization)
@non_test_receiver  # TODO can we extend django.dispatch.receiver or mock
def start_subscription(sender, instance, **kwargs):
    data = {"plan": PlanType.base.value, "email": instance.owner.email}
    serializer = SubscribeSerializer(data=data, context={"organization": instance})
    if serializer.is_valid():
        serializer.save()


@receiver([signals.post_delete, property_activated], sender=Property)
@non_test_receiver  # TODO can we extend django.dispatch.receiver or mock
def modify_billing_quantity(sender, instance, **kwargs):
    _update_subscription_quantity(instance)

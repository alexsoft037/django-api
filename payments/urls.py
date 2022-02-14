from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("credit-cards", views.CreditCardViewSet, base_name="pay_cc")
router.register("guest-credit-cards", views.GuestCreditCardViewSet, base_name="guest_pay_cc")
router.register("charges", views.ChargeViewSet, base_name="pay_charge")
router.register("plans", views.PricingPlanViewSet, base_name="pay_plan")
router.register("subscriptions", views.SubscribeViewSet, base_name="pay_sub")
router.register("disputes", views.DisputeViewSet, base_name="pay_disp")
router.register("coupons", views.CouponViewSet, base_name="pay_coup")
router.register("plaid", views.PlaidViewSet, base_name="plaid")
router.register("plaid_transactions", views.PlaidTransactionViewSet, base_name="transactions")
router.register("billing", views.BillingDetailsViewSet, base_name="billing")

# urlpatterns = [
#     url(r'^billing/$', BillingDetailsView.as_view(), name='billing_details')
# ]
urlpatterns = router.urls

from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"airbnb/webhook", views.AirbnbWebhookViewSet, base_name="airbnb-wh")
router.register(r"airbnb", views.AirbnbAuthViewSet, base_name="airbnb")
router.register(r"slack", views.SlackAuthViewSet, base_name="slack")
router.register(r"stripe", views.StripeAuthViewSet, base_name="stripe")
router.register(r"google", views.GoogleAuthViewSet, base_name="google")
router.register(r"mailchimp", views.MailchimpAuthViewSet, base_name="mailchimp")
router.register(r"", views.AppViewSet, base_name="appmarket")

slashless = DefaultRouter(trailing_slash=False)
slashless.register(r"airbnb/webhook", views.AirbnbWebhookViewSet, base_name="airbnb-wh")

urlpatterns = router.urls + slashless.urls

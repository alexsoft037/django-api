from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()

router.register(r"", views.NotificationViewSet, base_name="notification")
router.register(r"twilio", views.TwilioReplyViewSet, base_name="twilio-webhook")

urlpatterns = router.urls

from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(
    r"notification", views.VerificationNotificationViewSet, base_name="verification-notification"
)
urlpatterns = router.urls

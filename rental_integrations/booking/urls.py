from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"", views.BookingViewSet, base_name="booking-integration")

urlpatterns = router.urls

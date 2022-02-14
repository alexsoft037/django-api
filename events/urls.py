from rest_framework.routers import DefaultRouter

from .views import ReservationEventViewSet

router = DefaultRouter()

router.register(
    r"reservations/(?P<object_id>[0-9])/events",
    ReservationEventViewSet,
    base_name="reservation-events",
)

urlpatterns = router.urls

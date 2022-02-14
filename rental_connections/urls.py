from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"", views.RentalConnectionViewSet, base_name="rental-connections")

urlpatterns = router.urls

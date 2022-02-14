from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"", views.TripAdvisorViewSet, base_name="tripadvisor")
router.register(r"cozmo-sync", views.TripAdvisorSyncViewSet, base_name="tripadvisor-sync")

urlpatterns = router.urls

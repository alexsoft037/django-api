from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"", views.ReservationAutomationViewSet, base_name="mail-template-default")

urlpatterns = router.urls

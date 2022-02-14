from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"", views.ExpediaViewSet, base_name="expedia")

urlpatterns = router.urls

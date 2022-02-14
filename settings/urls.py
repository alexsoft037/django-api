from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"settings", views.OrganizationSettingsViewSet, base_name="settings")

urlpatterns = router.urls

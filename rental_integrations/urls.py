from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"settings", views.IntegrationSettingViewSet, base_name="intergration-setting")

urlpatterns = router.urls

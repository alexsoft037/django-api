from rest_framework.routers import DefaultRouter

from chat.views import ChatSettingsViewSet

router = DefaultRouter()

router.register(r"settings", ChatSettingsViewSet, base_name="chat-settings")

urlpatterns = router.urls

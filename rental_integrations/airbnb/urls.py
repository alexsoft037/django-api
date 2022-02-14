from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()

router.register(r"", views.AirbnbViewSet, base_name="airbnb")

urlpatterns = router.urls

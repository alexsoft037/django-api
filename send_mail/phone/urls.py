from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()

router.register(r"numbers", views.NumberViewSet, base_name="numbers")

urlpatterns = router.urls

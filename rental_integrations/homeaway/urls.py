from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()

router.register(r"", views.HomeAwayAccountViewSet, base_name="homeaway")
router.register(r"(?P<pk>[0-9])/2fa", views.Homeaway2faViewSet, base_name="homeaway-2fa")
urlpatterns = router.urls

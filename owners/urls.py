from django.conf.urls import url
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"owners", views.OwnerViewSet, base_name="owners")

urlpatterns = [
    url(r"^owners/invite/", views.OwnerInviteView.as_view(), name="owner-invite")
]

urlpatterns += router.urls

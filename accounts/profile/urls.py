from django.conf.urls import url
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
# router.register("organization", views.OrganizationView, base_name="acc_org")
router.register("shadow", views.ShadowLoginViewSet, base_name="acc_shadow")
router.register("team", views.TeamViewSet, base_name="acc_team")

urlpatterns = [
    url(r"^organization/plan/$", views.PlanSettingsView.as_view()),
    url(r"^organization/$", views.OrganizationView.as_view()),
    url(r"^organization/payments/$", views.PaymentSettingsView.as_view()),
    url(r"^organization/add_feature/$", views.AddFeatureView.as_view()),
    url(r"^organization/remove_feature/$", views.RemoveFeatureView.as_view())
] + router.urls

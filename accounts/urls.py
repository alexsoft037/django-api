from django.conf.urls import include, url
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("permissions", views.PermissionViewSet, base_name="acc_perms")
router.register("tokens", views.TokenViewSet, base_name="acc_tokens")
router.register("org_membership", views.OrgMembershipViewSet, base_name="acc_org_memberships")

urlpatterns = [
    url(r"^social/google/$", views.GoogleLogin.as_view(), name="google_login"),
    url(r"^", include("rest_auth.urls")),
    url(
        r"^registration/verify-email/$", views.VerifyEmailView.as_view(), name="rest_verify_email"
    ),
    url(r"^registration/", include("rest_auth.registration.urls")),
    url(
        r"^invitation/(?P<key>[^/.]+)/$", views.GetInvitationView.as_view(), name="get_invitation"
    ),
    url(r"^invite/", views.UserInviteView.as_view(), name="acc_invite"),
] + router.urls

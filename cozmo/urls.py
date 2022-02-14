"""cozmo URL Configuration.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.11/topics/http/urls/

Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))

"""
import logging

from django.conf.urls import include, url
from django.contrib import admin
from django.http import HttpResponse
from django.views.generic import RedirectView
from rest_framework.routers import DefaultRouter
from rest_framework.status import HTTP_200_OK
from rest_framework_swagger.views import get_swagger_view

from accounts.views import PhoneLoginView
from send_mail.tasks import parse_email
from send_mail.views import MessageViewSet, ConversationInboxViewSet

admin.site.site_header = "Cozmo Administration"
admin.site.site_title = "Cozmo Administration"


schema_view = get_swagger_view(title="Cozmo API")

logger = logging.getLogger(__name__)


def get_status_view(request):
    return HttpResponse(status=HTTP_200_OK)


def test(request):
    if True:
        parse_email(2685)
    else:
        from send_mail.choices import Status
        from send_mail.models import ParseEmailTask
        for each in ParseEmailTask.objects.exclude(status=Status.completed):
            parse_email(each.pk)
    return HttpResponse(status=HTTP_200_OK)


router = DefaultRouter()
router.register(r"messages", MessageViewSet, base_name="messages")
router.register(r"threads", ConversationInboxViewSet, base_name="conversation-inbox")

urlpatterns = [
    url(r"^test/", test, name="test"),
    url(r"^doc/$", schema_view, name="swagger-ui"),
    url(r"^service/status/$", get_status_view, name="status"),
    url(r"^api/v1/", include(("public_api.urls", "public_api"), namespace="v1")),
    url(r"^api-auth/", include("rest_framework.urls", namespace="rest_framework")),
    url(r"^accounts/", include("allauth.urls")),
    url(
        r"^account/profile/$",
        RedirectView.as_view(url="/", permanent=True),
        name="profile-redirect",
    ),
    url(r"^admin/", admin.site.urls),
    url(r"^auth/", include("accounts.urls")),
    url(r"^auth/", include("accounts.profile.urls")),
    url(r"^auth/vendor_login/", PhoneLoginView.as_view(), name="rest_phone_login"),
    url(r"^crm/", include("crm.urls")),
    url(r"^", include(("listings.urls", "listings"), namespace="property")),
    url(r"^", include(("listings.calendars.urls", "listings.calendars"), namespace="calendars")),
    url(r"^", include(("events.urls", "events"), namespace="events")),
    url(r"^", include(("search.urls", "search"), namespace="search")),
    url(
        r"^integrations/airbnb/",
        include(
            ("rental_integrations.airbnb.urls", "rental_integrations.airbnb"), namespace="airbnb"
        ),
    ),
    url(
        r"^integrations/booking/",
        include(
            ("rental_integrations.booking.urls", "rental_integrations.booking"),
            namespace="booking",
        ),
    ),
    url(
        r"^integrations/expedia/",
        include(
            ("rental_integrations.expedia.urls", "rental_integrations.expedia"),
            namespace="expedia",
        ),
    ),
    url(
        r"^integrations/homeaway/",
        include(
            ("rental_integrations.homeaway.urls", "rental_integrations.homeaway"),
            namespace="homeaway",
        ),
    ),
    url(
        r"^integrations/tripadvisor/",
        include(
            ("rental_integrations.trip_advisor.urls", "rental_integrations.trip_advisor"),
            namespace="tripadvisor",
        ),
    ),
    url(
        r"^integrations/",
        include(("rental_integrations.urls", "rental_integrations"), namespace="integrations"),
    ),
    url(
        r"^marketplace/",
        include(("app_marketplace.urls", "app_marketplace"), namespace="appmarket"),
    ),
    url(r"^notifications/", include(("notifications.urls", "notifications"), namespace="notify")),
    url(r"^payments/", include(("payments.urls", "payments"), namespace="payments")),
    url(r"^pois/", include(("pois.urls", "pois"), namespace="pois")),
    url(r"^conversations/", include(("send_mail.urls", "send_mail"), namespace="mails")),
    url(r"^responses/", include(("chat.urls", "chat"), namespace="chat")),
    url(
        r"^templates/",
        include(("message_templates.urls", "message_templates"), namespace="templates"),
    ),
    url(r"^automation/", include(("automation.urls", "automation"), namespace="automation")),
    url(r"^vendors/", include(("vendors.urls", "vendors"), namespace="vendors")),
    url(
        r"^rental-connections/",
        include(("rental_connections.urls", "rental_connections"), namespace="rental_connections"),
    ),
    url(
        r"^rental-network/",
        include(("rental_network.urls", "rental_network"), namespace="rental_network"),
    ),
    url(r"^", include(("owners.urls", "owners"), namespace="owners")),
    url(r"^", include(("settings.urls", "settings"), namespace="settings")),
    url(r"^", include(("dashboard.urls", "dashboard"), namespace="dashboard")),
]

urlpatterns += router.urls

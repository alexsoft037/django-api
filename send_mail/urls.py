from django.conf.urls import url
from django.urls import include
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()

urlpatterns = [
    url(r"^", include(("send_mail.phone.urls", "send_mail.phone"), namespace="phone")),
]

router.register(r"webhook/nexmo", views.NexmoWebhookViewset, base_name="nexmo-webhook")
router.register(r"webhook/sendgrid", views.SendgridParseWebhookView, base_name="sendgrid-webhook")
router.register(r"forwarding", views.ForwardingEmailViewSet, base_name="forwarding-email")
router.register(r"", views.ConversationView, base_name="conversation")

slashless = DefaultRouter(trailing_slash=False)
slashless.register(r"webhook/nexmo", views.NexmoWebhookViewset, base_name="nexmo-webhook")

urlpatterns += router.urls + slashless.urls

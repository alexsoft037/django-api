from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("tickets", views.TicketViewSet, base_name="crm_tickets")
router.register("messages", views.MessageViewSet, base_name="crm_messages")
router.register("contacts", views.ContactViewSet, base_name="crm_contacts")

urlpatterns = router.urls

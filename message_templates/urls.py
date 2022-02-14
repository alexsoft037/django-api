from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()

router.register(r"base_templates", views.DefaultTemplateViewSet, base_name="mail-template-default")
router.register(r"custom_templates", views.TemplateViewSet, base_name="mail-template")
router.register(r"welcome_templates", views.WelcomeTemplateViewSet, base_name="welcome-template")
router.register(r"tags", views.TagViewSet, base_name="mail-tags")
router.register(r"variables", views.VariableViewSet, base_name="mail-variable")

urlpatterns = router.urls

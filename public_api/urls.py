from rest_framework.routers import DefaultRouter, SimpleRouter

from . import views, views_sandbox as sandbox

default_router = DefaultRouter()
router_without_trailing_slash = SimpleRouter(trailing_slash=False)

routers = [default_router, router_without_trailing_slash]

for router in routers:
    router.register("properties", views.PropertyViewSet, base_name="properties")
    router.register(
        r"properties/(?P<prop_id>[0-9]+)/stayrequirements",
        views.StayRequirementsViewSet,
        base_name="rentals-stayrequirement",
    )
    router.register(
        "properties/(?P<prop_id>[0-9]+)/quotes", views.QuoteViewSet, base_name="properties-quote"
    )
    router.register(
        "properties/(?P<prop_id>[0-9]+)/rates", views.RateViewSet, base_name="properties-rate"
    )
    router.register(
        "properties/(?P<prop_id>[0-9]+)/fees", views.FeeViewSet, base_name="properties-fee"
    )
    # Only to make one endpoint with and without trailing_slash
    router.register("reservations", views.ReservationViewSet, base_name="reservations")

    router.register("sandbox/properties", sandbox.PropertyViewSet, base_name="s-properties")
    router.register(
        r"properties/(?P<prop_id>[0-9]+)/stayrequirements",
        sandbox.StayRequirementsViewSet,
        base_name="s-rentals-stayrequirement",
    )
    router.register(
        "properties/(?P<prop_id>[0-9]+)/quotes",
        sandbox.QuoteViewSet,
        base_name="s-properties-quote",
    )
    router.register(
        "properties/(?P<prop_id>[0-9]+)/rates", sandbox.RateViewSet, base_name="s-properties-rate"
    )
    router.register(
        "properties/(?P<prop_id>[0-9]+)/fees", sandbox.FeeViewSet, base_name="s-properties-fee"
    )
    router.register(
        "properties/(?P<prop_id>[0-9]+)/availability",
        views.AvailabilityViewSet,
        base_name="properties-availability",
    )
    router.register("sandbox/reservations", sandbox.ReservationViewSet, base_name="s-quote")

urlpatterns = [item for sublist in routers for item in sublist.urls]

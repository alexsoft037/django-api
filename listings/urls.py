from django.conf.urls import url
from rest_framework.routers import DefaultRouter

from . import views
from .public_views import InquiryView

router = DefaultRouter()

router.register(r"properties", views.PropertyViewSet, base_name="property")
router.register(
    r"properties/(?P<prop_id>[0-9]+)/images", views.ImageViewSet, base_name="property-photo"
)
router.register(
    r"properties/(?P<prop_id>[0-9]+)/videos", views.VideoViewSet, base_name="property-video"
)
router.register(
    r"properties/(?P<prop_id>[0-9]+)/rooms", views.RoomViewSet, base_name="property-room"
)
router.register(
    r"properties/(?P<prop_id>[0-9]+)/pois", views.PointOfInterestViewSet, base_name="property-poi"
)
router.register(
    r"properties/(?P<prop_id>[0-9]+)/blockings",
    views.BlockingViewSet,
    base_name="property-blocking",
)
router.register(
    r"properties/(?P<prop_id>[0-9]+)/availability",
    views.AvailabilityViewSet,
    base_name="property-availability",
)
router.register(
    r"properties/(?P<prop_id>[0-9]+)/turndays",
    views.TurndaysViewSet,
    base_name="property-turndays",
)
router.register(
    r"properties/(?P<prop_id>[0-9]+)/quotes", views.QuoteViewSet, base_name="property-quote"
)
router.register(
    r"properties/(?P<prop_id>[0-9]+)/seasonal_rates",
    views.SeasonalRateViewSet,
    base_name="property-seasonal-rates",
)
router.register(
    r"properties/(?P<prop_id>[0-9]+)/scheduling_assistant",
    views.SchedulingAssistantViewSet,
    base_name="scheduling_assistant",
)


router.register(r"charges/discounts", views.DiscountViewSet, base_name="charge-discount")
router.register(r"charges/fees", views.FeeViewSet, base_name="charge-fee")
router.register(r"charges/rates", views.RateViewSet, base_name="charge-rate")
router.register(r"charges/taxes", views.TaxViewSet, base_name="charge-tax")
router.register(r"properties-groups", views.GroupViewSet, base_name="properties-groups")
router.register(r"features", views.FeatureViewSet, base_name="features")
router.register(r"external-listings", views.ExternalListingViewSet, base_name="external-listings")

router.register(r"reservations/calendar", views.ReservationCalendarView, base_name="multi-cal")
router.register(r"reservations", views.ReservationViewSet, base_name="reservations")
router.register(
    r"reservations/(?P<reservation_id>[0-9]+)/notes",
    views.ReservationNoteViewSet,
    base_name="reservation-notes",
)

urlpatterns = [
    url(r"^charges/$", views.ChargeView.as_view()),
    url(r"^inquiries/$", InquiryView.as_view()),
]

urlpatterns += router.urls

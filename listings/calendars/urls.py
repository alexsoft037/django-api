from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()

router.register(
    r"calendars/calendar_colors", views.CalendarColorViewSet, base_name="calendar_color"
)
router.register(
    r"calendars/external_calendar_events",
    views.ExternalCalendarEventViewSet,
    base_name="external_calendar_events",
)

router.register(r"calendars", views.CalendarViewSet, base_name="calendar")
router.register(
    r"calendars/(?P<cozmo_cal_id>[^/.]+)/external",
    views.ExternalCalendarViewSet,
    base_name="calendar-external",
)

urlpatterns = router.urls

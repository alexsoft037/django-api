from django.conf.urls import url
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()

router.register(r"jobs/calendar", views.JobCalendarViewSet, base_name="jobs-calendar")
router.register(
    r"jobs/reservation-calendar", views.JobReservationCalView, base_name="jobs-calendar"
)
router.register(r"jobs/status", views.JobStatusViewSet, base_name="jobs-status")
router.register(r"jobs/report", views.JobReportViewSet, base_name="jobs-report")
router.register(r"properties", views.VendorPropertyViewSet, base_name="vendor_props")

router.register(r"jobs", views.JobViewSet, base_name="jobs")
router.register(
    r"jobs/(?P<job_id>[0-9])/checklists", views.ChecklistViewSet, base_name="job-check"
)
router.register(
    r"jobs/(?P<job_id>[0-9])/checklists/(?P<checklist_item_id>[0-9])/instructions",
    views.InstructionViewSet,
    base_name="job-check-instructions",
)

router.register(r"vendors", views.VendorViewSet, base_name="vendors")
router.register(
    r"vendors/(?P<vendor_id>[0-9]+)/assignments",
    views.AssignmentViewSet,
    base_name="vendors-assigment",
)

urlpatterns = [
    url(r"^invite/", views.VendorInviteView.as_view(), name="vendor-invite")
]

urlpatterns += router.urls

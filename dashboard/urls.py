from django.conf.urls import url

from dashboard.views import DashboardViewSet

urlpatterns = [url(r"^dashboard/?$", DashboardViewSet.as_view(), name="dashboard")]

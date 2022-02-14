from rest_framework import viewsets
from rest_framework.filters import SearchFilter

from accounts.views import UserInviteView
from cozmo_common.filters import OrganizationFilter
from cozmo_common.mixins import ApplicationPermissionViewMixin
from cozmo_common.pagination import PageNumberTenPagination
from owners.models import Owner
from . import serializers


class OwnerViewSet(ApplicationPermissionViewMixin, viewsets.ModelViewSet):
    """Read, create, update and delete RentalConnection"""

    queryset = Owner.objects.all().order_by("id")
    serializer_class = serializers.OwnerSerializer
    filter_backends = (
        OrganizationFilter,
        SearchFilter,
    )
    search_fields = (
        "first_name",
        "last_name",
    )
    pagination_class = PageNumberTenPagination


class OwnerInviteView(UserInviteView):
    serializer_class = serializers.OwnerInviteSerializer
    org_lookup_field = "user__organizations"

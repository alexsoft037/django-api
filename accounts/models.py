from uuid import uuid4

from django.contrib.auth.models import AbstractUser, Permission
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.functional import cached_property
from guardian.ctypes import get_content_type
from guardian.shortcuts import get_users_with_perms
from guardian.utils import get_group_obj_perms_model, get_user_obj_perms_model
from rest_framework.authtoken.models import Token as _Token

from cozmo.storages import UploadImageTo
from cozmo_common.db.fields import PhoneField
from cozmo_common.db.models import TimestampModel
from cozmo_common.enums import ChoicesEnum
from .choices import ApplicationTypes, RoleTypes
from .managers import OwnerManager
from .permissions import MANAGE_ORGANIZATION_PERMISSION, OrganizationPermissions
from .utils import jwt_encode_handler, jwt_payload_no_expiry_handler as jwt_payload_handler


class Timezone(models.Model):

    name = models.CharField(max_length=35)


class Organization(TimestampModel):
    name = models.CharField(max_length=80, blank=True)
    email = models.EmailField(blank=True)

    state = models.CharField(max_length=100, blank=True, default="")
    city = models.CharField(max_length=100, default="", blank=True)
    address1 = models.CharField(max_length=150, default="", blank=True)
    address2 = models.CharField(max_length=150, default="", blank=True)
    postal_code = models.CharField(max_length=8, default="", blank=True)
    phone = PhoneField(default="", blank=True)

    description = models.TextField(blank=True)
    timezone = models.ForeignKey(
        Timezone, blank=True, null=True, default=None, on_delete=models.SET_NULL
    )
    applications = ArrayField(
        models.PositiveIntegerField(choices=ApplicationTypes.choices()), default=list, blank=True
    )

    class Meta:
        permissions = OrganizationPermissions.choices()

    @property
    def owner(self):
        users_qs = get_users_with_perms(self)
        permission = Permission.objects.get(
            content_type=get_content_type(self), codename=MANAGE_ORGANIZATION_PERMISSION
        )
        user_permission = get_user_obj_perms_model(self)
        group_permission = get_group_obj_perms_model(self)
        group_field = f"groups__{group_permission.group.field.related_query_name()}__permission"
        return users_qs.filter(
            models.Q(
                **{f"{user_permission.user.field.related_query_name()}__permission": permission}
            )
            | models.Q(**{group_field: permission})
        ).first()

    def __str__(self):
        return f"{self.name} pk={self.id}"


class User(AbstractUser):
    """Base user model of Cozmo."""

    # Types that can be changed by the user
    class AllowedTypes(ChoicesEnum):
        Small_Owner = "SO"
        House_Broker = "HB"
        Accountant = "AC"
        Owner = "OW"

    class VendorTypes(ChoicesEnum):
        Cleaner = "CL"
        Deliverer = "DE"
        Maintainer = "MA"

    class SpecialTypes(ChoicesEnum):
        Api_User = "AU"

    allowed_types = AllowedTypes.choices()
    vendor_types = VendorTypes.choices()
    special_types = SpecialTypes.choices()

    ACCOUNT_TYPES = allowed_types + vendor_types + special_types

    account_type = models.CharField(max_length=2, choices=ACCOUNT_TYPES)
    role = models.IntegerField(choices=RoleTypes.choices(), null=True, default=RoleTypes.admin)
    middle_name = models.CharField(max_length=30, blank=True, default="")
    phone = PhoneField(null=True, default=None, blank=True)
    avatar = models.ImageField(upload_to=UploadImageTo("user/avatar"), default="", blank=False)
    organizations = models.ManyToManyField(Organization, through="accounts.Membership", blank=True)

    invited = models.BooleanField(default=False)
    date_updated = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        permissions = (("view_user", "Can view users"),)

    @property
    def is_vendor(self):
        return any(v[0] == self.account_type for v in self.VendorTypes.choices())

    @property
    def is_api_user(self):
        return self.account_type == self.SpecialTypes.Api_User.value

    @property
    def is_group_contributor(self):
        return self.role == RoleTypes.contributor_group.value

    @property
    def is_owner(self):
        return self.role == RoleTypes.owner.value

    @cached_property
    def organization(self):
        return self.organizations.filter(membership__is_default=True).first()


class OwnerUser(User):

    objects = OwnerManager()

    class Meta:
        proxy = True


class Token(_Token):

    key = models.CharField(max_length=300, editable=False, unique=True)
    name = models.CharField(max_length=50)
    user = models.OneToOneField(User, on_delete=models.PROTECT)
    is_sandbox = models.BooleanField(default=False)

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    date_updated = models.DateTimeField(auto_now=True, editable=False)

    def generate_key(self):
        try:
            user = self.user
        except User.DoesNotExist:
            self.user = User.objects.create(
                username=str(uuid4()), account_type=User.SpecialTypes.Api_User.value
            )
            user = self.user
            Membership.objects.create(user=user, organization=self.organization, is_default=True)
        payload = jwt_payload_handler(user)
        return jwt_encode_handler(payload)


class Membership(models.Model):

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    is_default = models.BooleanField(default=False)

    def validate_unique(self, exclude=None):
        super().validate_unique(exclude=exclude)

        other_default = self.objects.exclude(pk=self.pk).filter(
            is_default=True, user_id=self.user_id, organization_id=self.organization_id
        )
        if self.is_default and other_default.exists():
            raise ValidationError(["Only one organization can be default"])


class OrgMembership(models.Model):
    parent = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    child = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")

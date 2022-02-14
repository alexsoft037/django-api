from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.fields import CharField, IntegerField, SerializerMethodField, ListField

from accounts.choices import ApplicationTypes
from accounts.models import Membership, Organization
from accounts.serializers import OrganizationSubscriptionSerializer, UserDataSerializer
from accounts.signals import user_role_changed, org_feature_changed
from accounts.utils import jwt_encode_handler, jwt_payload_handler
from cozmo_common.fields import ChoicesField, NestedRelatedField
from listings.models import Group, GroupUserAssignment
from listings.serializers import GroupSerializer
from settings.serializers import OrganizationSettingsSerializer
from .models import PaymentSettings, PlanSettings, choose_plan

User = get_user_model()


class PaymentSettingsSerializer(serializers.ModelSerializer):

    serializer_choice_field = ChoicesField

    class Meta:
        model = PaymentSettings
        fields = ("payment_schedule",)
        read_only_fields = ("organization",)


class PlanSettingsSerializer(serializers.ModelSerializer):

    serializer_choice_field = ChoicesField

    plan = serializers.CharField()

    class Meta:
        model = PlanSettings
        fields = (
            "team",
            "properties",
            "organization",
            "plan",
            "month_days",
            "cancellation_policy",
            "trip_advisor_sync",
            "booking_sync",
        )
        read_only_fields = ("organization",)

    def validate(self, data):
        plan = data.pop("plan", None)

        if plan and plan != choose_plan(data["team"], data["properties"]):
            raise serializers.ValidationError("Wrong plan was chosen")
        return data


class OrganizationMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ("id", "name", "email", "description", "phone")


class OrganizationSerializer(OrganizationMinimalSerializer):

    # users = SerializerMethodField()
    plan = PlanSettingsSerializer(source="plansettings", read_only=True)
    settings = OrganizationSettingsSerializer(read_only=True)
    serializer_choice_field = ChoicesField

    subscription = OrganizationSubscriptionSerializer(read_only=True)

    class Meta:
        model = Organization
        fields = (
            "id",
            "name",
            "address1",
            "address2",
            "state",
            "city",
            "postal_code",
            "description",
            "phone",
            "email",
            # "users",
            "plan",
            "applications",
            "settings",
            "subscription",
        )

    def get_users(self, obj):
        return UserDataSerializer(
            obj.user_set.exclude(account_type=User.SpecialTypes.Api_User),
            many=True,
            read_only=True,
        ).data


class AddAppSerializer(serializers.ModelSerializer):
    feature = ChoicesField(choices=ApplicationTypes.choices(), write_only=True)
    features = ListField(
        child=ChoicesField(choices=ApplicationTypes.choices()),
        source="get_applications_display",
        read_only=True,
    )

    class Meta:
        model = Organization
        fields = ("feature", "features")

    def validate(self, attrs):
        feature = attrs.get("feature")
        org = self.instance
        apps = org.applications
        if feature in apps:
            raise ValidationError("App already exists")
        return attrs

    def update(self, instance, validated_data):
        feature = validated_data.get("feature")
        org = self.instance
        org.applications.append(feature)
        org.save()

        org_feature_changed.send(sender=instance.__class__, instance=instance)
        return org


class RemoveAppSerializer(AddAppSerializer):

    def validate(self, attrs):
        feature = attrs.get("feature")
        org = self.instance
        apps = org.applications
        if feature not in apps:
            raise ValidationError("App does not exist")
        return attrs

    def update(self, instance, validated_data):
        feature = validated_data.get("feature")
        self.instance.applications.remove(feature)
        self.instance.save()

        org_feature_changed.send(sender=instance.__class__, instance=instance)
        return self.instance


class NestedOrganization(NestedRelatedField):

    serializer = OrganizationSerializer

    def get_queryset(self):
        return self.parent.instance.organizations


class UserPlanSerializer(UserDataSerializer):

    organization = NestedOrganization()
    organizations = OrganizationMinimalSerializer(read_only=True, many=True)
    account_type = ChoicesField(choices=User.AllowedTypes.choices())

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "account_type",
            "avatar",
            "phone",
            "first_name",
            "last_name",
            "email",
            "organization",
            "organizations",
            "role",
        )
        read_only_fields = ("email",)
        extra_kwargs = {"phone": {"allow_null": False}}


class ShadowLoginSerializer(serializers.Serializer):
    """Read token from cache and if valid, return a shadowed login user with new token"""

    secret = serializers.CharField(write_only=True)
    token = serializers.CharField(read_only=True)

    def validate(self, data):
        secret_key = f"shadow_{data['secret']}"
        secret = cache.get(secret_key)
        cache.delete(secret_key)
        if secret:
            shadow_id, user_id = secret.split(",")
        else:
            raise serializers.ValidationError({"secret": "Invalid secret"})

        shadow = (
            User.objects.exclude(is_superuser=True)
            .exclude(is_staff=True)
            .filter(id=shadow_id)
            .first()
        )
        if shadow is None:
            raise serializers.ValidationError({"secret": "Invalid secret"})

        data["shadow"] = shadow
        data["user"] = User.objects.filter(id=user_id).first()
        return data

    @property
    def data(self):
        validated_data = self._validated_data
        payload = jwt_payload_handler(validated_data["user"])
        payload["shadow"] = validated_data["shadow"].id
        payload["exp"] = timezone.now() + timedelta(hours=1)

        return {
            "token": jwt_encode_handler(payload),
            "user": UserPlanSerializer(instance=validated_data["shadow"]).data,
        }

    def create(self, validated_data):
        return validated_data["user"]


class OrganizationManageSerializer(serializers.ModelSerializer):

    username = CharField(required=True, write_only=True)

    class Meta:
        model = Organization
        fields = ("username",)

    def validate_username(self, username):
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            raise serializers.ValidationError("User does not exist")

    def update(self, instance, validated_data):
        kwargs = {"user": validated_data.pop("username"), "organization": instance}
        if self.context["action"] == "create":
            Membership.objects.create(**kwargs)
        elif self.context["action"] == "delete":
            Membership.objects.filter(**kwargs).delete()
        return instance

    def create(self, validated_data):
        return {}


class TeamPropertyGroupSerializer(GroupSerializer):
    class Meta:
        model = Group
        fields = ("id", "name", "description", "properties_count")


class TeamGroupUserAssignmentSerializer(serializers.ModelSerializer):

    name = CharField(source="group.name")
    description = CharField(source="group.description")

    class Meta:
        model = GroupUserAssignment
        fields = ("name", "description", "id")
        extra_kwargs = {"id": {"source": "group_id"}}


class BasicTeamSerializer(serializers.ModelSerializer):
    is_verified = SerializerMethodField()

    def get_is_verified(self, obj):
        return obj.emailaddress_set.filter(verified=True).exists()

    class Meta:
        model = User
        fields = (
            "id",
            "avatar",
            "email",
            "username",
            "first_name",
            "middle_name",
            "last_name",
            "phone",
            "account_type",
            "is_active",
            "last_login",
            "date_joined",
            "role",
            "is_verified",
        )
        extra_kwargs = {"last_login": {"read_only": True}, "date_joined": {"read_only": True}}


class TeamSerializer(BasicTeamSerializer):
    groups = TeamGroupUserAssignmentSerializer(
        many=True, source="group_user_assignments", read_only=True
    )
    group_ids = serializers.ListField(
        child=IntegerField(), write_only=True, allow_empty=True, required=False
    )

    class Meta:
        model = User
        fields = BasicTeamSerializer.Meta.fields + ("groups", "group_ids")

    def update(self, instance, validated_data):
        groups = validated_data.pop("group_ids", None)
        if groups is not None:
            for group_id in groups:
                GroupUserAssignment.objects.update_or_create(
                    group_id=group_id, user_id=instance.id
                )
            instance.group_user_assignments.exclude(group_id__in=groups).delete()

        original_role = instance.role
        updated_instance = super().update(instance, validated_data)

        role = validated_data.get("role", None)
        if role and role != original_role:
            user_role_changed.send(sender=instance.__class__, instance=instance)

        return updated_instance

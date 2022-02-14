from itertools import groupby
from operator import itemgetter

from django.contrib.auth import get_user_model
from drf_extra_fields.fields import DateTimeRangeField
from rest_framework import serializers
from rest_framework.fields import BooleanField, HiddenField
from rest_framework.validators import UniqueTogetherValidator

from accounts.choices import RoleTypes
from accounts.profile.serializers import BasicTeamSerializer
from accounts.serializers import RegisterSerializer
from cozmo_common import fields, fields as cf
from cozmo_common.fields import ChoicesField, DefaultOrganization, E164PhoneField
from cozmo_common.serializers import OrderSerializer
from listings.models import Property
from listings.serializers import (
    LocationSerializer,
    PropertyCalSerializer,
    PropertyMinimalSerializer,
    RoomSerializer,
    SchedulingAssistantSerializer,
)
from owners.models import Owner
from vendors.models import Expense, Job, Vendor
from . import models

User = get_user_model()


class VendorForAssignmentMinimalSerializer(serializers.ModelSerializer):
    user = BasicTeamSerializer()

    class Meta:
        model = models.Vendor
        fields = ("user", "id")


class VendorMinimalSerializer(VendorForAssignmentMinimalSerializer):
    class Meta(VendorForAssignmentMinimalSerializer):
        model = models.Vendor
        fields = VendorForAssignmentMinimalSerializer.Meta.fields + ("assigned_properties",)

    def is_valid(self, raise_exception=False):
        if self.instance and self.instance.user.email == self.initial_data.get("email", None):
            self.initial_data.pop("email")
        return super().is_valid(raise_exception=raise_exception)


class AssignmentMinimalSerializer(serializers.ModelSerializer):

    vendor = VendorForAssignmentMinimalSerializer()

    class Meta:
        model = models.Assignment
        fields = ("id", "cleaning_fee", "order", "vendor")


class AssignmentSerializer(serializers.ModelSerializer):

    property = cf.NestedRelatedField(
        queryset=Property.objects.existing(), serializer=PropertyMinimalSerializer, source="prop"
    )
    vendor_id = serializers.HiddenField(default=cf.ContextDefault("vendor_id"))

    class Meta:
        model = models.Assignment
        fields = ("id", "cleaning_fee", "order", "property", "vendor_id")
        validators = [
            UniqueTogetherValidator(
                queryset=models.Assignment.objects.all(), fields=("vendor_id", "prop")
            )
        ]


class ReassingListSerializer(serializers.ListSerializer):
    def update(self, instance, validated_data):
        if validated_data:
            instance.update(**validated_data[0])
        return instance


class ReassingSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Assignment
        fields = ("id", "vendor")
        list_serializer_class = ReassingListSerializer


class InstructionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Instruction
        fields = ("id", "name", "done")


class ChecklistItemBaseSerializer(serializers.BaseSerializer):
    """This is a walk around for drf-yasg denying to handle nested serializer."""

    instruction = InstructionSerializer(many=True, required=False)


class ChecklistItemSerializer(ChecklistItemBaseSerializer, serializers.ModelSerializer):
    class Meta:
        model = models.ChecklistItem
        fields = ("id", "name", "image", "instruction")

    def create(self, validated_data):
        instruction = validated_data.pop("instruction", [])

        instance = super().create(validated_data)

        models.Instruction.objects.bulk_create(
            models.Instruction(checklist_item=instance, **item) for item in instruction
        )
        return instance


class JobMinimalSerializer(serializers.ModelSerializer):

    type = cf.ChoicesField(choices=models.Job.Jobs.choices(), source="job_type")
    status = cf.ChoicesField(choices=models.Job.Statuses.choices(), required=False)
    time_frame = DateTimeRangeField(allow_null=False)

    class Meta:
        model = models.Job
        fields = ("id", "time_frame", "base_cost", "type", "status", "assignee")


class JobReassingSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Job
        fields = ("id", "assignee")
        list_serializer_class = ReassingListSerializer


class JobAssigneeSerializer(JobMinimalSerializer):

    assignee = VendorMinimalSerializer()


class VendorInviteSerializer(RegisterSerializer):
    account_type = ChoicesField(
        choices=User.VendorTypes.choices(), default=User.VendorTypes.Cleaner.value
    )
    organization = HiddenField(default=DefaultOrganization())
    role = ChoicesField(choices=RoleTypes.choices(), default=RoleTypes.cleaner.value)
    invited = BooleanField(default=True)
    phone = E164PhoneField()

    class Meta(RegisterSerializer.Meta):
        fields = (
            "email",
            "account_type",
            "role",
            "organization",
            "invited",
            "first_name",
            "last_name",
            "phone",
        )

    def create(self, request):
        user = super().create(request)
        Vendor.objects.create(user=user, invited_by=request.user)
        return user


class VendorSerializer(VendorMinimalSerializer):

    notification_preference = cf.ChoicesField(
        choices=models.Vendor.Notifies.choices(),
        required=False,
        default=models.Vendor.Notifies.Email.value,
    )
    payout_preference = cf.ChoicesField(
        choices=models.Vendor.Payments.choices(), default=models.Vendor.Payments.Cash.value
    )
    jobs_count = serializers.IntegerField(read_only=True)

    # date_joined = serializers.DateTimeField(source="user.date_joined", read_only=True)
    user = BasicTeamSerializer(read_only=True)
    phone = serializers.CharField(write_only=True, source="user.phone")
    first_name = serializers.CharField(write_only=True, source="user.first_name")
    last_name = serializers.CharField(write_only=True, source="user.last_name")
    email = serializers.CharField(write_only=True, source="user.email")
    account_type = serializers.ChoiceField(
        choices=User.VendorTypes.choices(), write_only=True, source="user.account_type"
    )

    class Meta:
        model = models.Vendor
        fields = (
            "assigned_properties",
            "id",
            "jobs_count",
            "notification_enabled",
            "notification_preference",
            "payout_preference",
            "user",
            "phone",
            "first_name",
            "last_name",
            "email",
            "account_type",
        )

    def validate(self, data):
        if "user" in data:
            data["user"] = self._validate_user_data(data["user"])
        return data

    def _validate_user_data(self, user_data):
        args = []
        kwargs = {"data": user_data}

        if self.partial:
            args.append(self.instance.user)
            kwargs["partial"] = True

        user_serializer = VendorUserSerializer(*args, **kwargs, context=self.context)
        user_serializer.is_valid(raise_exception=True)
        user = user_serializer.save(self.context["request"])
        return user


class WorkLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.WorkLog
        fields = ("event", "date_created")


class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Expense
        fields = ("date_disbursed", "disbursed", "name", "description", "category", "value", "id")


class JobReportSerializer(serializers.ModelSerializer):

    job_id = serializers.PrimaryKeyRelatedField(
        source="job", queryset=Job.objects.all(), write_only=True
    )

    class Meta:
        model = models.Report
        exclude = ("date_updated", "job")


class JobStatusSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(models.Job.Statuses.choices())

    class Meta:
        model = models.Job
        fields = ("id", "status")

    def create(self, validated_data):
        status = validated_data["status"]
        job_id = validated_data["id"]
        job = self.Meta.model.objects.get(pk=job_id)
        job.status = status
        job.save(update_fields=["status"])
        return job

    def validate_status(self, obj):
        return obj

    def validate(self, data):
        return data


class OwnerForJobSerializer(serializers.ModelSerializer):

    first_name = serializers.CharField(source="user.first_name", write_only=True, required=False)
    last_name = serializers.CharField(source="user.last_name", write_only=True, required=False)
    email = serializers.CharField(source="user.email", write_only=True, required=False)
    phone = serializers.CharField(source="user.phone", write_only=True, required=False)

    class Meta:
        model = Owner
        fields = ("id", "first_name", "last_name", "email", "phone")


class PropertyJobSerializer(serializers.ModelSerializer):

    serializer_choice_field = fields.ChoicesField

    full_address = serializers.CharField(read_only=True)
    cover_image = serializers.ReadOnlyField()
    # thumbnail = ReadOnlyField()
    rooms = RoomSerializer(many=True, source="room_set", read_only=True)
    location = LocationSerializer(required=False, allow_null=True)
    owner = OwnerForJobSerializer(required=False)

    class Meta:
        model = Property
        fields = (
            "id",
            "name",
            "full_address",
            "cover_image",
            # "thumbnail",
            "location",
            "max_guests",
            "locale",
            "bedrooms",
            "bathrooms",
            "rooms",
            "owner",
            "time_zone",
        )


class JobSerializer(JobMinimalSerializer):

    checklist = ChecklistItemSerializer(many=True, read_only=True)
    property = PropertyJobSerializer(source="prop", read_only=True)
    assignee = VendorSerializer(read_only=True)
    assignee_id = serializers.PrimaryKeyRelatedField(
        queryset=models.Vendor.objects.all(), source="assignee", write_only=True
    )
    expenses = ExpenseSerializer(source="expense_set", required=False, many=True)
    events = WorkLogSerializer(source="worklog_set", read_only=True, many=True)
    reports = JobReportSerializer(source="report_set", read_only=True, many=True)

    class Meta:
        model = models.Job
        exclude = ("job_type", "date_created", "date_updated")
        extra_kwargs = {"prop": {"write_only": True}}

    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)
    #     self._notify_message = None

    def validate_date(self, date):
        date._bounds = "[]"
        return date

    def validate(self, data):
        old_status = getattr(self.instance, "status", None)

        if old_status == models.Job.Statuses.Cancelled.value:
            if "assignee" in data:
                data["status"] = models.Job.Statuses.Not_Accepted.value
                self._notify_message = "Job was cancelled"
            else:
                raise serializers.ValidationError("Cannot change cancelled task")
        if "assignee" in data:
            self._notify_message = "New job assignment. Please reply with {}.".format(
                " or ".join(self.Meta.model.REPLY_MAP)
            )

        return data

    def create(self, validated_data):
        expenses = validated_data.pop("expense_set", list())

        job = self.Meta.model.objects.create(**validated_data)
        for expense in expenses:
            Expense.objects.create(job=job, **expense)

        return job

    def update(self, instance, validated_data):
        expenses = validated_data.pop("expense_set", None)

        if expenses:
            Expense.objects.exclude(
                job=instance, id__in=[e.get("id", None) for e in expenses if e.get("id", None)]
            ).delete()
            for expense in expenses:
                expense_id = expense.pop("id", None)
                Expense.objects.update_or_create(job=instance, id=expense_id, defaults=expense)

        return super().update(instance, validated_data)

    # def save(self):
    #     instance = super().save()
    #     # if self._notify_message:
    #     #     Notification.objects.create(
    #     #         channel=Notification.Channels.SMS.value,
    #     #         content=self._notify_message,
    #     #         to_id=instance.assignee.user_id,
    #     #         content_object=instance,
    #     #     )
    #     return instance


class JobCalendarListSerializer(serializers.ListSerializer):
    @property
    def data(self):
        data = super().data
        return [
            {"date": date, "jobs": {job["status"]: job["count"] for job in jobs}}
            for date, jobs in groupby(data, itemgetter("date"))
        ]


class JobCalendarSerializer(serializers.Serializer):

    date = serializers.DateField()
    status = cf.ChoicesField(choices=models.Job.Statuses.choices())
    count = serializers.IntegerField()

    class Meta:
        list_serializer_class = JobCalendarListSerializer


class JobReservationSerializer(PropertyCalSerializer):

    jobs = JobAssigneeSerializer(many=True, source="job_included")
    schedule_settings = SchedulingAssistantSerializer(source="scheduling_assistant")
    assigned_cleaners = AssignmentMinimalSerializer(
        many=True, read_only=True, source="assignment_set"
    )

    class Meta:
        model = PropertyCalSerializer.Meta.model
        fields = (
            "id",
            "name",
            "full_address",
            "cover_image",
            "jobs",
            "reservations",
            "schedule_settings",
            "assigned_cleaners",
        )


class VendorUserSerializer(RegisterSerializer):

    organization = serializers.HiddenField(default=cf.DefaultOrganization())

    class Meta:
        model = User
        fields = (
            "phone",
            "email",
            "first_name",
            "last_name",
            "avatar",
            "account_type",
            "is_active",
            "organization",
            "role",
        )

    def create(self, request):
        instance = super().create(request)
        instance.set_unusable_password()
        instance.is_active = self.validated_data.get("is_active", True)
        instance.save()
        return instance


class PropertyAssignmentSerializer(serializers.ModelSerializer):

    id = serializers.IntegerField(source="vendor.id")
    user = BasicTeamSerializer(source="vendor.user")

    class Meta:
        model = models.Assignment
        fields = ("id", "user", "order", "cleaning_fee")


class VendorOrderSerializer(OrderSerializer):

    lookup_field = "vendor_id"

    class Meta:
        model = models.Assignment


class VendorPropertySerializer(PropertyMinimalSerializer):

    vendors = serializers.SerializerMethodField()
    schedule_settings = SchedulingAssistantSerializer(source="scheduling_assistant")

    class Meta:
        depth = 1
        model = Property
        fields = ("id", "name", "full_address", "cover_image", "vendors", "schedule_settings")

    def get_vendors(self, instance):
        assignments = instance.assignment_set.select_related("vendor").order_by("order")
        return PropertyAssignmentSerializer(instance=assignments, many=True).data

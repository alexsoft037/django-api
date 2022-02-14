from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import DateTimeRangeField
from django.db import models

from cozmo.storages import UploadImageTo
from cozmo_common.db.models import TimestampModel
from cozmo_common.enums import ChoicesEnum

User = get_user_model()


class Job(TimestampModel):
    """Job which needs to be done by Vendor in Property."""

    class Jobs(ChoicesEnum):

        Checkup = "JCU"
        Clean = "JCL"
        Delivery = "JDE"
        Greet = "JGR"
        Repair = "JRE"

    class Statuses(ChoicesEnum):
        # Job sent to vendor, but not accepted yet
        Not_Accepted = "SNA"
        # Job sent ot vendor and read, but not accepted yet
        Not_Accepted_Seen = "SAS"
        # Job is accepted, but not started yet. Should be in this state until cancelled or
        # start on day of job
        Accepted = "SNS"
        # Job is accepted and started, but not completed or passes the alloted time
        Incomplete = "SIN"
        # Job is in progress
        In_Progress = "SIP"
        # Job is started, but no longer in progress
        Paused = "SPA"
        # Job is complete
        Completed = "SCO"
        # Job is cancelled or stopped because of issues out of vendor control
        Unable_To_Complete = "SUN"
        # Job is cancelled anytime after accepting
        Cancelled = "SCA"
        # Job has been declined
        Declined = "SDC"

    REPLY_MAP = {"ACCEPT": Statuses.Accepted.value, "REJECT": Statuses.Declined.value}

    time_frame = DateTimeRangeField(null=True)
    time_estimate = models.DurationField(blank=True, default=timedelta(minutes=60))
    job_type = models.CharField(max_length=3, choices=Jobs.choices())
    status = models.CharField(
        max_length=3, choices=Statuses.choices(), default=Statuses.Not_Accepted.value, blank=True
    )

    base_cost = models.DecimalField(max_digits=8, decimal_places=2)
    description = models.TextField(max_length=1000, default="", blank=True)
    entry_instructions = models.TextField(max_length=1000, default="", blank=True)
    # TODO Move entry_instructions to separate model
    date_added = models.DateTimeField(auto_now_add=True, blank=True)
    is_active = models.BooleanField(default=True, blank=True)
    assignee = models.ForeignKey("Vendor", null=True, blank=True, on_delete=models.SET_NULL)
    prop = models.ForeignKey("listings.Property", on_delete=models.CASCADE)

    class Meta:
        permissions = (
            ("view_job", "Can view jobs"),
            ("change_job_status", "Can change job status"),
        )

    @property
    def cost_total(self):
        total = 0
        for expense in self.expense_set.all():
            total += expense.value
        return total


class WorkLog(TimestampModel):
    """
    Event and timestamp that tracks a vendor's job progress and milestones
    """

    class Event(ChoicesEnum):
        """
        State transitions:
        Accept > Decline
        Accept > Start <> Pause > Finish
        Accept > .. > Cancel

        Contact and Problem events can occur anytime and is independent of state
        """

        # Vendor accepts the job
        Accept = 1
        # Vendor declines the job offering
        Decline = 2
        # Vendor starts the job
        Start = 3
        # Vendor pauses the job and is not cleaning. Reasons could include needing
        # to pick up supplies or do something personal with the intention of coming back
        Pause = 4
        # Vendor stops the job with the intention of not coming back. May be deprecated for Cancel
        Stop = 5
        # Vendor finishes the job
        Finish = 6
        # Vendor communicates with the owner
        Contact = 7
        # Vendor reports a problem to the owner
        Problem = 8
        # Vendor cancels the job at any time after accepting
        Cancel = 9

        # Job was created and sent to vendor
        Init = 10

        # Job was seen for the first time by the vendor
        Seen = 11

        # Job was marked as incomplete by Cozmo based on specific criteria
        Incomplete = 12

        # Job was marked as finished, but also unable to be completed
        Finish_Unable = 13

        # Job was reassigned
        Reassign = 14

        # Experimental
        # Vendor enters geofence
        Arrive = 20
        # Vendor leaves geofence
        Leaves = 21

    job = models.ForeignKey(Job, related_name="worklog_set", on_delete=models.CASCADE)
    event = models.PositiveSmallIntegerField(choices=Event.choices())

    # Experimental with geofence events
    on_premise = models.BooleanField(default=False)

    class Meta:
        ordering = ("date_created",)
        permissions = (("view_worklog", "Can view work logs"),)


class Report(TimestampModel):
    image = models.ImageField(upload_to=UploadImageTo("vendors/report"), null=True, blank=True)
    job = models.ForeignKey("Job", related_name="report_set", on_delete=models.CASCADE)
    description = models.CharField(max_length=500, blank=True)
    is_problem = models.BooleanField(default=False)

    class Meta:
        permissions = (("view_report", "Can view reports"),)


class Expense(TimestampModel):
    """
    Tracks fees charged by vendor or any reimbursements. Credits may also be applied here by adding
    a negative value
    """

    class Category(ChoicesEnum):
        Service = "CSV"
        Reimbursement = "CRT"
        Supplies = "CSP"
        Refund = "CRF"
        Misc = "CMS"
        Other = "COT"

    job = models.ForeignKey(Job, related_name="expense_set", on_delete=models.CASCADE)
    value = models.DecimalField(max_digits=8, decimal_places=2)
    category = models.CharField(
        max_length=3, choices=Category.choices(), default=Category.Other.value
    )
    name = models.CharField(max_length=64)
    description = models.TextField(default="")
    disbursed = models.BooleanField(default=False)
    date_disbursed = models.DateTimeField(null=True, default=None)


class ChecklistItem(models.Model):
    """Parts of which job consists of."""

    name = models.CharField(max_length=100)
    image = models.ImageField(upload_to=UploadImageTo("vendors/tasks"), null=True, blank=True)
    date_updated = models.DateTimeField(auto_now=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True, editable=False)

    job = models.ForeignKey("Job", related_name="checklist", on_delete=models.CASCADE)


class Instruction(models.Model):
    """Details on how to perform a concrete item from Checklist as expected."""

    name = models.CharField(max_length=100)
    done = models.BooleanField(default=False, blank=True)
    date_updated = models.DateTimeField(auto_now=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True, editable=False)

    checklist_item = models.ForeignKey(
        "ChecklistItem", related_name="instruction", on_delete=models.CASCADE
    )


class Assignment(models.Model):
    """Association between Vendor and Property with pricing details."""

    vendor = models.ForeignKey("Vendor", on_delete=models.CASCADE)
    prop = models.ForeignKey("listings.Property", on_delete=models.CASCADE)

    cleaning_fee = models.DecimalField(max_digits=8, decimal_places=2)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ("vendor", "prop")
        permissions = (("view_assignment", "Can view assignments"),)


class Vendor(models.Model):
    """Person who works on keeping a property clean and functional."""

    class Notifies(ChoicesEnum):
        Email = "E"
        SMS = "S"

    class Payments(ChoicesEnum):
        Check = 0
        ACH = 1
        Cash = 2

    notification_preference = models.CharField(
        max_length=3, choices=Notifies.choices(), default=Notifies.Email.value, blank=True
    )
    notification_enabled = models.BooleanField(default=True, blank=True)
    payout_preference = models.SmallIntegerField(
        choices=Payments.choices(), default=Payments.Cash.value
    )
    date_updated = models.DateTimeField(auto_now=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True, editable=False)

    assigned_properties = models.ManyToManyField(
        "listings.Property", through="Assignment", through_fields=("vendor", "prop"), blank=True
    )
    invited_by = models.ForeignKey(User, related_name="+", null=True, on_delete=models.SET_NULL)
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    class Meta:
        permissions = (("view_vendor", "Can view vendors"),)

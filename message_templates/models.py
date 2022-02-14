from django.contrib.auth import get_user_model
from django.core.validators import RegexValidator
from django.db import models

from cozmo.storages import UploadImageTo
from listings.models import Reservation
from message_templates.choices import TemplateTypes
from message_templates.managers import WelcomeMessageManager

User = get_user_model()
word_validator = RegexValidator(
    regex=r"\w+", message="Only letters, numbers and underscore are allowed"
)


class BaseTemplate(models.Model):
    """Abstract base for email template."""

    name = models.CharField(max_length=512)
    subject = models.CharField(max_length=100, default="", blank=True)
    description = models.CharField(default="", max_length=250, blank=True)
    content = models.TextField()

    class Meta:
        abstract = True


class DefaultTemplate(BaseTemplate):
    """Predefined mail template."""


class Mail(models.Model):

    subject = models.TextField(default="", blank=True)
    text = models.TextField()
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, related_name="+", null=True)
    outgoing = models.BooleanField(default=True, blank=True)

    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["reservation", "date"])]


class Attachment(models.Model):

    name = models.CharField(max_length=250)
    url = models.FileField(upload_to=UploadImageTo("mail/attachments"))
    mail = models.ForeignKey(Mail, on_delete=models.CASCADE)


class Tag(models.Model):
    """
    Keyword describing a Template.

    Tag without organization reference is considered to be a global one.
    """

    name = models.CharField(max_length=15)
    organization = models.ForeignKey(
        "accounts.Organization", null=True, blank=True, on_delete=models.CASCADE
    )

    class Meta:
        unique_together = ("organization", "name")


class Template(BaseTemplate):
    """Organization-defined mail template."""

    headline = models.CharField(max_length=100, default="", blank=True)
    tags = models.ManyToManyField(Tag)
    template_type = models.CharField(
        max_length=1,
        choices=TemplateTypes.choices(),
        default=TemplateTypes.Email.value,
        blank=True,
    )
    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE)
    prop = models.ForeignKey(
        "listings.Property", default=None, blank=True, null=True, on_delete=models.CASCADE
    )
    group = models.ForeignKey(
        "listings.Group", default=None, blank=True, null=True, on_delete=models.CASCADE
    )

    class Meta:
        permissions = (("view_template", "Can view templates"),)


class WelcomeTemplate(Template):
    """Property Welcome Template"""
    objects = WelcomeMessageManager()

    class Meta:
        proxy = True


class Variable(models.Model):
    """Organization-defined variable to use in email templates."""

    display = models.CharField(max_length=20, default="")
    name = models.CharField(max_length=20, validators=[word_validator])
    value = models.CharField(max_length=50)
    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE)

    class Meta:
        unique_together = ("organization", "name")

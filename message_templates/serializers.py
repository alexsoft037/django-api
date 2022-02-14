import logging
import string
from enum import Enum
from io import BytesIO
from itertools import groupby

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.base import ContentFile
from django.core.mail import EmailMultiAlternatives
from django.template import loader
from django.utils.html import strip_tags
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.fields import (
    CharField,
    CurrentUserDefault,
    HiddenField,
    IntegerField,
    SerializerMethodField,
)
from weasyprint import HTML
from weasyprint.fonts import FontConfiguration

from app_marketplace.services import Google
from automation.models import ReservationAutomation
from cozmo_common.fields import ChoicesField, DefaultOrganization
from listings.models import Reservation
from pois.mappers import Mapper as PoiMapper
from rental_integrations.airbnb.service import AirbnbService
from . import mappers, models

logger = logging.getLogger(__name__)

MAX_NUMBER_OF_TAGS = 10


class DefaultUser(CurrentUserDefault):
    def set_context(self, serializer_field):
        try:
            super().set_context(serializer_field)
        except KeyError:
            self.user = serializer_field.context["user"]


class DefaultTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.DefaultTemplate
        fields = "__all__"


class FileListSerializer(serializers.Serializer):

    MAX_FILE = 10 * 1000000  # 10 MB, from SendGrid docs
    MAX_TOTAL = 30 * 1000000  # 30 MB, from SendGrid docs

    files = serializers.ListField(
        child=serializers.FileField(max_length=MAX_FILE, allow_empty_file=False, use_url=False),
        allow_empty=True,
    )

    def validate_files(self, files):
        total = sum(f.size for f in files)
        if total > self.MAX_TOTAL:
            raise ValidationError("Attachements are to big")
        return files


class SenderSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ("first_name", "last_name", "email", "avatar")


class MailAttachment(serializers.ModelSerializer):
    class Meta:
        model = models.Attachment
        fields = ("name", "url")


class BaseMailSerializer(serializers.ModelSerializer):
    reservation = IntegerField(source="reservation_id")
    sender = SerializerMethodField()
    attachments = SerializerMethodField()
    user = HiddenField(default=DefaultUser())
    organization = HiddenField(default=DefaultOrganization())

    class Meta:
        model = models.Mail
        exclude = ("id",)
        extra_kwargs = {"outgoing": {"read_only": True}, "subject": {"default": ""}}

    def get_sender(self, instance):
        return SenderSerializer(instance=instance.sender).data

    def get_attachments(self, instance):
        return MailAttachment(instance=instance.attachment_set, many=True).data

    def validate(self, data):
        organization = data.get("organization", None)
        if organization is None:
            raise ValidationError("User does not belong to Organization")

        try:
            reservation = (
                Reservation.objects.filter(
                    pk=data["reservation_id"], prop__organization=organization
                )
                .select_related("prop", "guest")
                .get()
            )
            data["prop"] = reservation.prop
        except ObjectDoesNotExist:
            raise ValidationError("Organization does not have reservation with given id")

        try:
            data["receiver"] = reservation.guest.email
        except ObjectDoesNotExist:
            raise ValidationError("Guest does not have email assigned")

        try:
            custom_vars = organization.variable_set.all().values("name", "value")
            data["text"] = mappers.Mapper(reservation, data["user"]).substitute(
                data["text"], custom_vars
            )
        except ValueError as e:
            raise ValidationError(e.args[0])

        return data

    def create(self, validated_data):
        """Send email message with optional attachments."""
        parsed_attatchment = tuple(
            (a.name, a.read()) for a in validated_data.get("attachments", [])
        )
        self._send_email(validated_data, attachments=parsed_attatchment)

        mail = super().create(
            {
                "subject": validated_data["subject"],
                "text": validated_data["text"],
                "sender": validated_data["user"],
                "reservation_id": validated_data["reservation_id"],
            }
        )

        models.Attachment.objects.bulk_create(
            models.Attachment(name=a[0], url=ContentFile(a[1], name=a[0]), mail=mail)
            for a in parsed_attatchment
        )

        return mail

    def _send_email(self, validated_data, attachments=None):
        raise NotImplementedError()


class MailSerializer(BaseMailSerializer):
    def _send_email(self, validated_data, attachments=None):
        html_content = validated_data["text"]

        email = EmailMultiAlternatives(
            subject=validated_data["subject"],
            body=strip_tags(html_content),
            from_email=getattr(validated_data["user"], "email", None),
            to=(validated_data["receiver"],),
            attachments=attachments,
        )
        email.attach_alternative(html_content, "text/html")
        try:
            email.send(fail_silently=False)
        except TypeError:
            # Bug in sendgrid-django: https://github.com/elbuo8/sendgrid-django/issues/61
            raise ValidationError("Could not send message (txt files are not supported)")
        except Exception as e:
            logger.info("Could not send email: %s", e.args)
            raise ValidationError("Could not send message")


class GmailSerializer(BaseMailSerializer):
    def _send_email(self, validated_data, attachments=None):
        html_content = validated_data["text"]

        g_app = validated_data["organization"].googleapp_set.only("credentials").last()
        google = Google(credentials=g_app.credentials)
        response = google.send_message(
            sender=getattr(validated_data["user"], "email", None),
            to=validated_data["receiver"],
            subject=validated_data["subject"],
            message_text=strip_tags(html_content),
        )
        if response is None:
            raise ValidationError("Could not send message")


class AirbnbMessageSerializer(BaseMailSerializer):
    thread_id = serializers.IntegerField(write_only=True)

    def _send_email(self, validated_data, attachments=None):
        app = validated_data["organization"].airbnbapp_set.only("access_token", "user_id").last()
        airbnb = AirbnbService(app.user_id, app.access_token)
        airbnb.push_message(validated_data.pop("thread_id"), validated_data["text"])


class RenderSerializer(BaseMailSerializer):
    def create(self, validated_data):
        html = HTML(string=validated_data["text"])
        out = BytesIO()
        html.write_pdf(
            out,
            attachments=validated_data.get("attachments", None),
            font_config=FontConfiguration(),
        )
        return out


class TagSerializer(serializers.ModelSerializer):

    organization = HiddenField(default=DefaultOrganization())

    class Meta:
        model = models.Tag
        fields = "__all__"


class TagListingField(serializers.RelatedField):

    default_error_messages = {
        "not_int": "{data} is not a valid id.",
        "not_exists": 'Tag with id "{data}" does not exist.',
    }

    queryset = models.Tag.objects.all()

    def to_representation(self, value):
        return TagSerializer(value).data

    def to_internal_value(self, data):
        try:
            return self.queryset.get(pk=int(data))
        except (ValueError, TypeError):
            self.fail("not_int", data=data)
        except ObjectDoesNotExist:
            self.fail("not_exists", data=data)


class TemplateScheduleSerializer(serializers.ModelSerializer):

    recipient_address = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    cc_address = serializers.ListField(
        child=serializers.EmailField(), allow_empty=True, required=False, allow_null=True
    )
    bcc_address = serializers.ListField(
        child=serializers.EmailField(), allow_empty=True, required=False, allow_null=True
    )

    class Meta:
        model = ReservationAutomation
        fields = (
            "id",
            "is_active",
            "days_delta",
            "event",
            "time",
            "method",
            "recipient_address",
            "recipient_type",
            "cc_address",
            "bcc_address"
        )
        extra_kwargs = {"organization": {"write_only": True}}


class TemplateSerializer(serializers.ModelSerializer):

    class TemplateVisibility(Enum):
        GLOBAL = "global"
        GROUP = "group"
        PROPERTY = "property"

    organization = HiddenField(default=DefaultOrganization())
    type = ChoicesField(
        source="template_type",
        choices=models.TemplateTypes.choices(),
        default=models.TemplateTypes.Email.value,
        required=False,
    )
    tags = TagListingField(many=True, required=False)
    schedules = TemplateScheduleSerializer(many=True, source="schedule_set", read_only=True)
    visibility = SerializerMethodField()

    class Meta:
        model = models.Template
        fields = (
            "id",
            "type",
            "name",
            "subject",
            "description",
            "headline",
            "content",
            "tags",
            "prop",
            "organization",
            "schedules",
            "visibility"
        )
        read_only_fields = ("organization", "external_id")

    def get_visibility(self, obj):
        """
        Returns the entity that owns this template. If it is global, then prop and group will not
        be set. If group visible, then group will be set while prop will not and vice versa.
        """
        group_id = obj.group_id
        prop_id = obj.prop_id
        if group_id:
            return self.TemplateVisibility.GROUP.value
        elif prop_id:
            return self.TemplateVisibility.PROPERTY.value
        return self.TemplateVisibility.GLOBAL.value

    # def validate_subject(self, subject):
    #     """
    #     Validate that string is using valid variables
    #     :param subject:
    #     :return:
    #     """
    #     pass
    #
    # def validate_content(self, content):
    #     """
    #     Validate that content is using valid variables
    #     :param content:
    #     :return:
    #     """
    #     pass

    def validate_tags(self, tags):
        number_of_tags = len(tags)
        if number_of_tags >= MAX_NUMBER_OF_TAGS:
            raise ValidationError(
                "Too many tags: {}, max: {}".format(number_of_tags, MAX_NUMBER_OF_TAGS)
            )
        return tags

    # def validate(self, data):
    #     org = data["organization"]
    #     prop = data.get("property", None)
    #     if prop is not None and not org.property_set.filter(pk=prop.pk).exists():
    #         raise ValidationError('Invalid pk "{}" - object does not exist.'.format(prop.pk))
    #     return data


class VariableSerializer(serializers.ModelSerializer):

    organization = HiddenField(default=DefaultOrganization())

    class Meta:
        model = models.Variable
        fields = ("name", "value", "organization")


class WelcomeTemplateSerializer(serializers.ModelSerializer):

    organization = HiddenField(default=DefaultOrganization())
    prop_name = CharField(source="prop.name", read_only=True)
    content = SerializerMethodField()

    class Meta:
        model = models.WelcomeTemplate
        fields = "__all__"

    def _get_sequence_char(self, i):
        numerator = string.digits[1:] + string.ascii_uppercase
        return numerator[i] if i <= len(numerator) - 1 else ""

    def get_content(self, obj):
        prop = obj.prop
        cover_image = prop.image_set.all().values_list("url").first()

        pois_queryset = prop.poi_set.all().order_by("category")
        grouped_pois = {k: v for k, v in groupby(pois_queryset, lambda p: p.category)}
        all_categories = PoiMapper.get_all_categories()

        i = 0
        template_pois = {}
        map_pois = []
        for key, category in all_categories.items():
            if key not in grouped_pois:
                continue
            template_pois[key] = dict(cat=category, pois=[])

            for poi in grouped_pois[key]:
                number = self._get_sequence_char(i)
                if poi.coordinates:
                    map_pois.append(
                        dict(
                            longitude=poi.coordinates.longitude,
                            latitude=poi.coordinates.latitude,
                            label=number,
                        )
                    )
                template_pois[key]["pois"].append(dict(poi=poi, i=number))
                i += 1

        context = {
            "property_name": prop.name,
            "cover_image": cover_image[0] if cover_image else None,
            "check_in": getattr(prop.booking_settings.check_in_out, "check_in_to", ""),
            "check_out": getattr(prop.booking_settings.check_in_out, "check_out_until", ""),
            "address": prop.full_address,
            "arrival_instruction": getattr(prop.arrival_instruction, "description", ""),
            "longitude": getattr(prop.location.longitude, "longitude", ""),
            "latitude": getattr(prop.location.latitude, "latitude", ""),
            # "house_rules": prop.houserules_set.all(),
            # "things_to_do": prop.things_to_do,
            "pois": template_pois,
            "map_pois": map_pois,
        }

        return loader.render_to_string(obj.template + ".html", context)

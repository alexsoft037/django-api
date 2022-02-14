import json
import logging
import re
from abc import abstractmethod
from datetime import datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from io import BytesIO

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.fields import (
    BooleanField,
    CharField,
    HiddenField,
    SerializerMethodField,
    empty,
    IntegerField,
)
from rest_framework.status import HTTP_200_OK
from weasyprint import HTML
from weasyprint.fonts import FontConfiguration

from automation.utils import html_to_text
from cozmo_common.fields import ChoicesField, DefaultUser, DefaultOrganization
from crm.models import Contact
from crm.serializers import ContactSerializer, UserSerializer
from listings.calendars.models import ExternalCalendar
from listings.choices import ReservationStatuses, FeeTypes, SecurityDepositTypes
from listings.models import ExternalListing, Reservation, ReservationFee
from send_mail.choices import DeliveryStatus, MessageType, NexmoMessageType
from send_mail.models import Conversation, EmailMessage, ForwardingEmail, Message, ParseEmailTask
from send_mail.phone.models import Number
from vendors.models import Job
from . import models

logger = logging.getLogger(__name__)

MAX_NUMBER_OF_TAGS = 10


class FileListSerializer(serializers.Serializer):

    MAX_FILE = 10 * 1_000_000  # 10 MB, from SendGrid docs
    MAX_TOTAL = 30 * 1_000_000  # 30 MB, from SendGrid docs

    files = serializers.ListField(
        child=serializers.FileField(max_length=MAX_FILE, allow_empty_file=False, use_url=False),
        allow_empty=True,
    )

    def validate_files(self, files):
        total = sum(f.size for f in files)
        if total > self.MAX_TOTAL:
            raise ValidationError("Attachements are to big")
        return files


class AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Attachment
        fields = ("name", "url")


class SenderSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ("first_name", "last_name", "email", "avatar")


class MailAttachment(serializers.ModelSerializer):
    class Meta:
        model = models.Attachment
        fields = ("name", "url")


class MessageSerializer(serializers.ModelSerializer):
    conversation_id = serializers.PrimaryKeyRelatedField(
        queryset=Conversation.objects.all(), write_only=True, source="conversation"
    )
    recipient = serializers.CharField(read_only=True)
    type = ChoicesField(choices=MessageType.choices(), allow_null=False)
    sender = HiddenField(default=DefaultUser())

    class Meta:
        model = models.Message
        exclude = ("conversation", "date_created")
        read_only_fields = (
            "outgoing",
            "external_id",
            "recipient_info",
            "sender",
            "delivered",
            "recipient",
        )

    def create(self, validated_data):
        """Send email message with optional attachments."""
        parsed_attachment = tuple(
            (a.name, a.read()) for a in validated_data.get("attachments", [])
        )

        validated_data["sender"] = validated_data["sender"].email
        message = super().create(validated_data)

        models.Attachment.objects.bulk_create(
            models.Attachment(name=a[0], url=ContentFile(a[1], name=a[0]), message=message)
            for a in parsed_attachment
        )

        return message


class ConversationSerializer(serializers.ModelSerializer):
    reservation_id = serializers.PrimaryKeyRelatedField(read_only=True, source="reservation")
    messages = serializers.SerializerMethodField()
    participants = SerializerMethodField()
    supported_messages = SerializerMethodField()

    class Meta:
        model = models.Conversation
        fields = (
            "id",
            "reservation_id",
            "participants",
            "unread",
            "supported_messages",
            "messages",
        )
        read_only_fields = ("reservation",)

    def get_messages(self, instance):
        messages = instance.messages.all().order_by("date_delivered")
        return MessageSerializer(messages, many=True).data

    def get_participants(self, instance):
        message = Message.objects.filter(conversation_id=instance.id).first()
        participants = (
            dict(
                sender=UserSerializer(message.sender).data,
                recipient=ContactSerializer(message.recipient).data,
            )
            if message is not None
            else list()
        )
        return participants

    def get_supported_messages(self, instance):
        message_types = list()
        reservation = instance.reservation
        if hasattr(reservation, "external_reservation"):
            message_types.append(MessageType.api.name)
        guest = reservation.guest
        number_exists = Number.objects.filter(
            organization=instance.reservation.prop.organization
        ).exists()
        if number_exists and hasattr(guest, "phone"):
            message_types.append(MessageType.sms.name)
        if hasattr(guest, "email"):
            message_types.append(MessageType.email_managed.name)
        return message_types


class ConversationReservationSerializer(serializers.ModelSerializer):
    status = CharField(source="get_status_display")
    source = CharField(source="get_source_display")

    class Meta:
        model = Reservation
        fields = ("id", "status", "source")


class ConversationGuestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = ("full_name", "avatar")


class MinimalConversationInboxSerializer(serializers.ModelSerializer):

    reservation = ConversationReservationSerializer(source="conversation.reservation")
    unread = BooleanField(source="conversation.unread")
    guest = ConversationGuestSerializer(source="conversation.reservation.guest")
    thread_id = IntegerField(source="conversation.id")
    message_id = IntegerField(source="id")

    class Meta:
        model = models.Message
        fields = (
            "thread_id",
            "unread",
            "guest",
            "text",
            "date_delivered",
            "reservation",
            "message_id",
        )
        read_only_fields = (
            "thread_id",
            "guest",
            "text",
            "date_delivered",
            "reservation",
            "message_id",
        )

    def update(self, instance, validated_data):
        conversation = validated_data.pop("conversation", None)
        if conversation:
            Conversation.objects.filter(id=instance.conversation_id).update(**conversation)

        return super().update(instance, validated_data)


class ConversationInboxSerializer(MinimalConversationInboxSerializer):
    pass


class MailSerializer(MessageSerializer):
    # TODO update this
    # TODO sender for emails may need to be of a different type

    class Meta(MessageSerializer.Meta):
        model = models.EmailMessage
        exclude = ("conversation", "external_id")

    def validate_subject(self, subject):
        if not subject:
            self.fail("required")
        return subject

    def validate(self, attrs):
        conversation = attrs["conversation"]
        guest = conversation.reservation.guest

        if guest.email is None:
            raise ValidationError("Guest does not have a valid email")

        return attrs

    def create(self, validated_data):
        conversation = validated_data["conversation"]
        guest = conversation.reservation.guest
        html_text = validated_data.get("html_text", None)
        if html_text:
            validated_data["text"] = html_to_text(html_text)
        validated_data["recipient"] = guest.email
        recipient_info = {"cc": "", "bcc": ""}
        validated_data["recipient_info"] = recipient_info

        previous_email = (
            conversation.messages.filter(type=MessageType.email.value).order_by("-pk").last()
        )
        if previous_email:
            validated_data["reply_to_reference"] = previous_email.external_email_id
        return super().create(validated_data)


class GmailSerializer(MessageSerializer):
    # TODO update this
    class Meta(MessageSerializer.Meta):
        model = models.EmailMessage
        exclude = ("conversation", "external_id")


class SMSMessageSerializer(MessageSerializer):
    # TODO update this
    class Meta(MessageSerializer.Meta):
        model = models.SMSMessage
        exclude = ("conversation", "subject")

    def validate(self, attrs):
        conversation = attrs["conversation"]
        guest = conversation.reservation.guest

        if guest.phone is None:
            raise ValidationError("Guest does not have a valid phone number")

        return attrs

    def create(self, validated_data):
        conversation = validated_data["conversation"]
        guest = conversation.reservation.guest
        validated_data["recipient_info"] = guest.phone
        return super().create(validated_data)


class APIMessageSerializer(MessageSerializer):
    class Meta(MessageSerializer.Meta):
        model = models.APIMessage
        exclude = ("conversation", "subject")

    def validate(self, attrs):
        # conversation_id = attrs["conversation_id"]
        conversation_id = attrs["conversation"].id

        conversation = get_object_or_404(Conversation, **{"pk": conversation_id})
        if not hasattr(conversation.reservation, "external_reservation"):  # TODO not best way
            raise ValidationError("Reservation does not support API messaging")

        return attrs

    def create(self, validated_data):
        conversation = validated_data["conversation"]
        recipient_info = {"thread_id": conversation.thread_id}
        validated_data["recipient_info"] = recipient_info
        validated_data["recipient"] = conversation.thread_id
        return super().create(validated_data)


class RenderSerializer(MessageSerializer):
    def create(self, validated_data):
        html = HTML(string=validated_data["text"])
        out = BytesIO()
        html.write_pdf(
            out,
            attachments=validated_data.get("attachments", None),
            font_config=FontConfiguration(),
        )
        return out


class ForwardingEmailSerializer(serializers.ModelSerializer):
    organization = HiddenField(default=DefaultOrganization())

    class Meta:
        model = ForwardingEmail
        fields = ("id", "name", "enabled", "organization", "address")
        read_only_fields = ("name", "address")


class NexmoWebhookSerializer(serializers.Serializer):
    msisdn = serializers.CharField()
    to = serializers.CharField()
    messageId = serializers.CharField()
    text = serializers.CharField()
    type = serializers.ChoiceField(choices=NexmoMessageType.choices())
    keyword = serializers.CharField()
    # message_timestamp = serializers.DateTimeField()

    # def validate_msisdn(self, phone):
    #     listing_id = str(listing_id)
    #     if listing_id == self.test_id:
    #         return listing_id
    #
    #     if not Listing.objects.filter(external_id=listing_id).exists():
    #         raise serializers.ValidationError(f"Listing {listing_id} does not exist")
    #     return listing_id
    #
    # def validate_to(self, phone):

    def create(self, validated_data):
        logger.debug("[NEXMO WEBHOOK]: Response - (%s) %s", HTTP_200_OK, str(validated_data))
        phone = validated_data["msisdn"]
        job = Job.objects.filter(assignee__user__phone=phone).last()
        if "yes" in validated_data["text"].lower():
            job.status = Job.Statuses.Accepted.value
        elif "checkin" in validated_data["text"].lower():
            job.status = Job.Statuses.In_Progress.value
        elif "finish" in validated_data["text"].lower():
            job.status = Job.Statuses.Completed.value
        elif "pause" in validated_data["text"].lower():
            job.status = Job.Statuses.Paused.value
        elif "cancel" in validated_data["text"].lower():
            job.status = Job.Statuses.Cancelled.value
        elif "decline" in validated_data["text"].lower():
            job.status = Job.Statuses.Declined.value
        else:
            job.status = Job.Statuses.Incomplete.value

        job.save(update_fields=["status"])

        # reservation = Reservation.objects.filter(
        #     guest__phone=phone).order_by("date_updated").last()
        # conversation = Conversation.objects.get(reservation=reservation)
        # Message.objects.create(
        #     outgoing=False,
        #     external_id=validated_data["messageId"],
        #     # sender=reservation.guest,
        #     # recipient=reservation.owner,
        #     delivered=True,
        #     text=validated_data["text"],
        #     type=MessageType.sms.value,
        #     conversation=conversation
        # )
        return HttpResponse(status=HTTP_200_OK)


class SendgridWebhookField(CharField):

    default_error_messages = {"invalidnumber": '"{input}" is not a valid number.'}

    def to_internal_value(self, data):
        if isinstance(data, list):
            data = data[0]
        return data

    def run_validation(self, data=empty):
        if isinstance(data, list):
            data = data[0]
        return super(SendgridWebhookField, self).run_validation(data)


class ParseEmailTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParseEmailTask
        fields = ("data", "status")

    def create(self, validated_data):
        parsed_attachment = tuple(
            (a.name, a.read()) for a in validated_data.pop("attachments", [])
        )

        instance = super().create(validated_data)

        models.ParseEmailAttachment.objects.bulk_create(
            models.ParseEmailAttachment(name=a[0], url=ContentFile(a[1], name=a[0]), task=instance)
            for a in parsed_attachment
        )

        return instance


class BaseEmailSerializer(serializers.Serializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.context_data = {
            "confirmation_code": None,
            "start_date": None,
            "end_date": None,
            "nights": None,
            "nightly": None,
            "base_total": None,
            "price_total": None,
            "guest_first_name": None,
            "guest_last_name": None,
            "guest_image": None,
            "guest_email": None,
            "guests_adults": None,
            "guests_children": None,
            "message": None,
            "listing_id": None,
            "thread_id": None,
        }
        self.soup = None
        self.guest = None
        self.reservation = None
        self.conversation = None
        self.intent = None
        self.source = None
        self.message_object = None

    def _get_decimal_from_match(self, value):
        assert isinstance(value, tuple), "Argument is expected to be a tuple"
        assert len(value) == 2, "Argument is expected to be of length 2"
        sign, val = value
        return Decimal("{}{}".format("-" if sign else "", val))

    def get_header(self, header):
        header = re.compile(r"{}:\s*(.+)\n".format(header)).findall(
            self.validated_data.get("headers")
        )
        if header:
            return header[0]
        return None

    def get_property_id(self):
        """
        Attempts to find property that the email is referring to
        :return: listings.models.Property object else None
        """
        listing_id = self.context_data.get("listing_id")

        # Via external listing object
        properties = ExternalListing.objects.filter(listing_id=listing_id).values_list(
            "prop", flat=True
        )
        if properties.exists() and len(properties) == 1:
            return properties.first()

        # Via external calendars
        properties = (
            ExternalCalendar.objects.filter(url__regex=r"{}".format(listing_id))
            .values_list("cozmo_cal__prop", flat=True)
            .distinct()
        )
        if properties.exists() and len(properties) == 1:
            return properties.first()

        # Via conversation (thread_id)
        properties = Conversation.objects.filter(thread_id=self.data.get("thread_id")).values_list(
            "reservation__prop", flat=True
        )
        if properties.exists() and len(properties) == 1:
            return properties.first()

        raise ValidationError("Property ID must exist")

    @abstractmethod
    def get_confirmation_code(self):
        pass

    @abstractmethod
    def get_message(self):
        pass

    @abstractmethod
    def get_stay_dates(self):
        pass

    @abstractmethod
    def get_listing_id(self):
        pass

    @abstractmethod
    def get_intent(self):
        pass

    @abstractmethod
    def get_guest_info(self):
        pass

    @abstractmethod
    def get_thread_id(self):
        pass

    @abstractmethod
    def handle_inquiry(self):
        pass

    @abstractmethod
    def handle_reservation(self):
        pass

    @abstractmethod
    def handle_message(self):
        pass

    @abstractmethod
    def handle_cancellation(self):
        pass

    @abstractmethod
    def get_fees(self):
        pass


class AirbnbEmailSerializer(BaseEmailSerializer):
    def handle_message(self):
        self.get_listing_id()
        self.get_message()
        self.get_guest_info()
        self.get_stay_dates()
        self.get_num_guests()
        self.get_thread_id()

    def handle_reservation(self):
        self.get_listing_id()
        self.get_guest_info()
        self.get_num_guests()
        self.get_message()
        self.get_confirmation_code()
        self.get_stay_dates()
        self.get_fees()
        self.get_thread_id()

    def handle_inquiry(self):
        self.get_listing_id()

    def get_fees(self):
        amount_pattern = re.compile(r"(−*)\$(\d+\.\d+)")
        payout = self.soup(text=re.compile(r"Payout"))
        if payout:
            payouts = [p.text for p in payout[0].find_parent("div").find_all("p")]

            costs = payouts[1:]
            assert re.compile(r"Payout").search(payouts[0]), "Payouts should be first in list"
            assert len(costs) % 2 == 0 and len(costs) >= 2, "Payouts should be > 1 and even"

            fees = list()
            match = re.compile(r"\$(\d+\.\d+) x (\d+) Nights").findall(payouts[1])
            if match:
                nightly, nights = match[0]
                self.context_data["nightly"] = nightly
                self.context_data["nights"] = int(nights)
                base_total_match = amount_pattern.findall(payouts[2])
                if base_total_match:
                    self.context_data["base_total"] = self._get_decimal_from_match(
                        base_total_match[0]
                    )

            it = iter(payouts[3:-2])
            for p in it:
                item = p
                value = next(it)
                fee_val = amount_pattern.findall(value)[0]
                fees.append((item.strip(" \n"), self._get_decimal_from_match(fee_val)))

            self.context_data["fees"] = fees

            if re.compile(r"Total").search(payouts[-2]):
                amt_val = amount_pattern.findall(payouts[-1])[0]
                self.context_data["price_total"] = self._get_decimal_from_match(amt_val)

    def get_thread_id(self):
        thread_node_pattern = re.compile(r"airbnb\.com/z/q/(\d+)")
        thread_id_node = self.soup.find("a", href=thread_node_pattern)
        self.context_data["thread_id"] = re.compile(thread_node_pattern).findall(
            thread_id_node["href"]
        )[0]

    def get_guest_info(self):
        subject = self.validated_data.get("subject")
        name_match = re.compile(r"Reservation confirmed - (\w+) (\w+) arrives").findall(subject)
        if name_match:
            first, last = name_match[0]
            self.context_data["guest_first_name"] = first
            self.context_data["guest_last_name"] = last

        guest_re = re.compile("users/show/(\d+)")
        guest_node = self.soup.findAll("a", href=guest_re)
        self.context_data["guest_external_id"] = guest_re.findall(guest_node[0]["href"])[0]
        self.context_data["guest_image"] = guest_node[0].findAll("img")[0].get("src")
        self.context_data["guest_name"] = guest_node[1].findAll("p")[0].text.strip(" \n")
        email = re.compile(r"Reply-to:.+<(\S+@\S+)>").findall(self.validated_data.get("headers"))
        if email:
            self.context_data["guest_email"] = email[0]

    def get_confirmation_code(self):
        code = self.soup(text=re.compile(r"[A-Z0-9]{10}"))
        if code:
            code_match = re.compile(r"([A-Z0-9]{10})").findall(code[0])
            if code_match:
                self.context_data["confirmation_code"] = code_match[0]

    def get_message(self):
        self.context_data["message"] = self.soup.find(
            "p", style=re.compile(r"background-color")
        ).text.strip(" \n")

    def get_stay_dates(self):
        stay_dates = self.soup(
            "p", text=re.compile(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d+, \d+")
        )
        if stay_dates:
            assert len(stay_dates) >= 2, "Stay dates must have multiple matches"
            # Date pattern matches dates like "Dec 01, 2019"
            date_pattern = "%b %d, %Y"
            self.context_data["start_date"] = datetime.strptime(
                stay_dates[-2].text.strip(" \n"), date_pattern
            ).date()
            self.context_data["end_date"] = datetime.strptime(
                stay_dates[-1].text.strip(" \n"), date_pattern
            ).date()

    def get_listing_id(self):
        pattern = "https://www.airbnb.com/rooms/(\d+)"
        r = re.compile(pattern)
        m = r.findall(self.validated_data.get("text"))
        if m:
            self.context_data["listing_id"] = m[0]

    def get_intent(self):
        subject = self.validated_data("subject")
        if "Reservation confirmed" in subject:
            self.intent = "new_reservation"
        elif "Reservation at" in subject:
            self.intent = "new_message"
        elif "Inquiry" in subject:
            self.intent = "new_inquiry"
        elif "Reservation canceled" in subject:
            self.intent = "reservation_canceled"
        elif "Reservation reminder" in subject:
            self.intent = "reservation_reminder"


class ParseEmailSerializer(serializers.Serializer):
    SPF = SendgridWebhookField()
    charsets = SendgridWebhookField()
    dkim = SendgridWebhookField()
    envelope = SendgridWebhookField()

    frm = SendgridWebhookField()
    headers = SendgridWebhookField()
    html = SendgridWebhookField()
    sender_ip = SendgridWebhookField()
    subject = SendgridWebhookField()
    text = SendgridWebhookField()
    to = SendgridWebhookField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.context_data = {
            "confirmation_code": None,
            "start_date": None,
            "end_date": None,
            "nights": None,
            "nightly": None,
            "base_total": None,
            "price_total": None,
            "guest_first_name": None,
            "guest_last_name": None,
            "guest_image": None,
            "guest_email": None,
            "guests_adults": None,
            "guests_children": None,
            "message": None,
            "listing_id": None,
            "thread_id": None,
            "cancellation_policy": None,
            "outgoing": False,
        }
        self.soup = None
        self.guest = None
        self.reservation = None
        self.conversation = None
        self.intent = None
        self.source = None
        self.message_object = None

    def validate(self, attrs):
        dkim = attrs.get("dkim")
        if "pass" not in dkim:
            raise ValidationError("DKIM did not pass")

        envelope = json.loads(attrs.get("envelope"))
        forwarding_addr_match = re.compile(r"(\w+)@\w+").findall(envelope.get("to")[0])
        if forwarding_addr_match:
            forwarding_name = forwarding_addr_match[0]
            email = ForwardingEmail.objects.filter(name__iexact=forwarding_name)
            if not email.exists():
                raise ValidationError("ForwardingEmail does not exist")
            attrs["organization"] = email[0].organization
        else:
            raise ValidationError("Must have forwarding match")
        return attrs

    def get_confirmation_code(self):
        code = self.soup(text=re.compile(r"[A-Z0-9]{10}"))
        if code:
            code_match = re.compile(r"([A-Z0-9]{10})").findall(code[0])
            if code_match:
                self.context_data["confirmation_code"] = code_match[0]

    def get_thread_id(self):
        if self.source == "airbnb":
            # Airbnb Thread id
            thread_node_pattern = re.compile(r"airbnb\.com/z/q/(\d+)")
            thread_id_node = self.soup.find("a", href=thread_node_pattern)
            self.context_data["thread_id"] = re.compile(thread_node_pattern).findall(
                thread_id_node["href"]
            )[0]
        if self.source in ["homeaway", "vrbo"]:
            self.context_data["thread_id"] = self.get_header("X-Mediated-Conversation-ID")

    def get_guest_info(self):
        guest_re = re.compile("users/show/(\d+)")
        guest_node = self.soup.findAll("a", href=guest_re)
        self.context_data["guest_external_id"] = guest_re.findall(guest_node[0]["href"])[0]
        self.context_data["guest_image"] = guest_node[0].findAll("img")[0].get("src")
        self.context_data["guest_name"] = guest_node[1].findAll("p")[0].text.strip(" \n")
        email = re.compile(r"Reply-to:.+<(\S+@\S+)>").findall(self.validated_data.get("headers"))
        if email:
            self.context_data["guest_email"] = email[0]

    def get_message(self):
        match = self.soup.find(
            "p", style=re.compile(r"background-color:#f2f3f3")
        ).text.strip(" \n")
        if match:
            self.context_data["message"] = match.get_text("\n").strip(" \n")

    def get_stay_dates(self):
        stay_dates = self.soup(
            "p", text=re.compile(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d+, \d+")
        )
        if stay_dates:
            assert len(stay_dates) >= 2, "Stay dates must have multiple matches"
            # Date pattern matches dates like "Dec 01, 2019"
            date_pattern = "%b %d, %Y"
            self.context_data["start_date"] = datetime.strptime(
                stay_dates[-2].text.strip(" \n"), date_pattern
            ).date()
            self.context_data["end_date"] = datetime.strptime(
                stay_dates[-1].text.strip(" \n"), date_pattern
            ).date()

    def get_message_content(self):
        # Listing id
        self.get_listing_id()

        # Message
        self.get_message()

        # Guest info
        self.get_guest_info()

        # Reservation start date, end date
        self.get_stay_dates()

        # Num guests
        self.get_num_guests()

        self.get_thread_id()

    def get_num_guests(self):
        num_guests_node = self.soup.find(text=re.compile(r"Guests"))
        if num_guests_node:
            num_guests_data = num_guests_node.findNext("p").text.strip(" \n")
            p = re.compile(r"^(\d+)$|^(\d+) adults?(, (\d+) child(ren)?)?(, (\d+) infants?)?$")
            match = p.findall(num_guests_data)
            if match:
                adult, adults, _, children, _, _, infants = match[0]
                self.context_data["guests_adults"] = int(adult or adults)
                self.context_data["guests_children"] = int(children or 0)
                self.context_data["guests_infants"] = int(infants or 0)

    def _get_decimal_from_match(self, value):
        assert isinstance(value, tuple), "Argument is expected to be a tuple"
        assert len(value) == 2, "Argument is expected to be of length 2"
        sign, val = value
        return Decimal("{}{}".format("-" if sign else "", val))

    def get_reservation_content(self):
        amount_pattern = re.compile(r"(−*)\$(\d+\.\d+)")

        # Listing id
        self.get_listing_id()

        # Guest
        subject = self.validated_data.get("subject")
        name_match = re.compile(r"Reservation confirmed - (\w+) (\w+) arrives").findall(subject)
        if name_match:
            first, last = name_match[0]
            self.context_data["guest_first_name"] = first
            self.context_data["guest_last_name"] = last

        self.get_guest_info()

        # Num guests
        self.get_num_guests()

        # Message content
        self.get_message()

        self.get_confirmation_code()

        # Reservation start date, end date
        self.get_stay_dates()

        # Reservation costs
        payout = self.soup(text=re.compile(r"Payout"))
        if payout:
            payouts = [p.text for p in payout[0].find_parent("div").find_all("p")]

            costs = payouts[1:]
            assert re.compile(r"Payout").search(payouts[0]), "Payouts should be first in list"
            assert len(costs) % 2 == 0 and len(costs) >= 2, "Payouts should be > 1 and even"

            fees = list()
            match = re.compile(r"\$(\d+\.\d+) x (\d+) Nights?").findall(payouts[1])
            if match:
                nightly, nights = match[0]
                self.context_data["nightly"] = nightly
                self.context_data["nights"] = int(nights)
                base_total_match = amount_pattern.findall(payouts[2])
                if base_total_match:
                    self.context_data["base_total"] = self._get_decimal_from_match(
                        base_total_match[0]
                    )

            it = iter(payouts[3:-2])
            for p in it:
                item = p
                value = next(it)
                fee_val = amount_pattern.findall(value)[0]
                fees.append((item.strip(" \n"), self._get_decimal_from_match(fee_val)))

            self.context_data["fees"] = fees

            if re.compile(r"Total").search(payouts[-2]):
                amt_val = amount_pattern.findall(payouts[-1])[0]
                self.context_data["price_total"] = self._get_decimal_from_match(amt_val)

        self.get_thread_id()

    def get_source(self):
        # Fetch from headers or from
        original_sender = re.compile(r"X-Original-Sender:\s*(\S+@\S+)").findall(
            self.validated_data.get("headers")
        )
        if original_sender:
            sender = original_sender[0]
            if sender in ["express@airbnb.com", "automated@airbnb.com"]:
                self.source = "airbnb"
            elif re.compile(r"messages\.homeaway\.com").search(sender):
                mediated_src = re.compile(r"X-Mediated-Site:\s*(\w+)").findall(
                    self.validated_data.get("headers")
                )
                if mediated_src:
                    self.source = {"vrbo": "vrbo", "homeaway": "homeaway"}.get(mediated_src[0])

        if re.compile(r"(express|automated)@airbnb.com").search(
            self.validated_data.get("headers")
        ):
            self.source = "airbnb"

        if not self.source:
            raise ValidationError("No source could be determined")

    def get_header(self, header):
        header = re.compile(r"{}:\s*(.+)\n".format(header)).findall(
            self.validated_data.get("headers")
        )
        if header:
            return header[0]
        return None

    def get_listing_id(self):
        if self.source == "airbnb":
            pattern = "https://www.airbnb.com/rooms/(\d+)"
            r = re.compile(pattern)
            m = r.findall(self.validated_data.get("text"))
            if m:
                self.context_data["listing_id"] = m[0]
        elif self.source in ["vrbo", "homeaway"]:
            self.context_data["listing_id"] = re.compile(
                r"X-Inquiry-Listing:\s*([a-zA-Z0-9\-]+)"
            ).findall(self.validated_data.get("headers"))[0]

    def get_intent(self):  # noqa: C901
        assert self.source is not None, "get_source() must be called first"
        if self.source == "airbnb":
            template = self.get_header("X-Template")
            self.intent = {
                "reservation/host_confirmation": "new_reservation",
                "messaging/new_message": "new_message",
                "reservation/inquiries/incoming_inquiry": "new_inquiry",
                "mdx_cancellation/reservation_canceled_by_guest_to_host": "reservation_canceled",
                "reservation/incoming_reservation": "reservation_request",
            }.get(template)
        elif self.source in ["vrbo", "homeaway"]:
            message_type = self.get_header("X-Mediated-Message-Type")
            if message_type:
                self.intent = {
                    "INQUIRY": "new_inquiry",
                    "RESERVATION_ACTION_EMAIL_BLANK": "new_message",
                    "INQUIRY_ACTION_EMAIL_BLANK": "new_message",
                }.get(message_type)
        if not self.intent:
            raise ValidationError("Unable to determine intent")

    def get_property_id(self):
        """
        Attempts to find property that the email is referring to
        :return: listings.models.Property object else None
        """
        listing_id = self.context_data.get("listing_id")

        # Via external listing object
        properties = ExternalListing.objects.filter(listing_id=listing_id).values_list(
            "prop", flat=True
        )
        if properties.exists() and len(properties) == 1:
            return properties.first()

        # Via external calendars
        properties = (
            ExternalCalendar.objects.filter(url__regex=r"{}".format(listing_id))
            .values_list("cozmo_cal__prop", flat=True)
            .distinct()
        )
        if properties.exists() and len(properties) == 1:
            return properties.first()

        # Via conversation (thread_id)
        properties = Conversation.objects.filter(thread_id=self.data.get("thread_id")).values_list(
            "reservation__prop", flat=True
        )
        if properties.exists() and len(properties) == 1:
            return properties.first()

        raise ValidationError("Property ID must exist")

    def get_conversation(self):
        conversation = Conversation.objects.filter(thread_id=self.context_data.get("thread_id"))
        if conversation.exists():
            self.conversation = conversation[0]
            return

        self.get_guest()

        self.reservation, _ = Reservation.objects.get_or_create(
            start_date=self.context_data.get("start_date"),
            end_date=self.context_data.get("end_date"),
            prop_id=self.get_property_id(),
            source=Reservation.Sources.Airbnb.value,  # TODO
            defaults=dict(
                guest=self.guest,
                price=self.context_data.get("price_total"),
                guests_adults=self.context_data.get("guests_adults"),
                guests_children=self.context_data.get("guests_children"),
                guests_infants=self.context_data.get("guests_infants"),
            ),
        )
        self.conversation, _ = Conversation.objects.get_or_create(reservation=self.reservation)

        thread_id = self.context_data.get("thread_id")

        if thread_id and self.conversation:
            self.conversation.thread_id = thread_id
            self.conversation.save()

    def get_guest(self):
        name = self.context_data.get("guest_name")

        guest = Contact.objects.filter(
            email=self.context_data.get("guest_email") or "",
            organization=self.validated_data["organization"],
        )

        if guest.exists():
            self.guest = guest.first()

            if not self.guest.avatar:
                self.guest.avatar = self.context_data.get("guest_image")
                self.guest.save()
        else:
            data = dict(
                email=self.context_data.get("guest_email") or "",
                organization=self.validated_data["organization"],
                first_name=self.context_data.get("guest_first_name") or name,
                last_name=self.context_data.get("guest_last_name") or "",
                avatar=self.context_data.get("guest_image"),
                external_id=self.context_data.get("guest_external_id") or "",
            )
            self.guest = Contact.objects.create(**data)

    def get_or_create_reservation(self):
        # Checks for inquiry first and/or matching reservation by code
        reservations = Reservation.objects.filter(
            Q(status=ReservationStatuses.Inquiry.value,
              prop_id=self.get_property_id(),
              start_date=self.context_data.get("start_date"),
              end_date=self.context_data.get("end_date"),
              source=Reservation.Sources.Airbnb.value,
              guest__email=self.context_data.get("guest_email")) |
            Q(external_id=self.context_data.get("confirmation_code")) |
            Q(confirmation_code=self.context_data.get("confirmation_code"))
        )
        code = self.context_data.get("confirmation_code")
        last_name = self.context_data.get("guest_last_name")
        if reservations.exists():
            self.reservation = reservations.first()
            self.guest = self.reservation.guest
            if not self.guest.avatar:
                self.guest.avatar = self.context_data.get("guest_image")
                self.guest.save()
            if last_name and not self.guest.last_name:
                self.guest.last_name = last_name
                self.guest.save()
            if code and self.reservation.confirmation_code != code:
                self.reservation.confirmation_code = code
                self.reservation.guests_adults = self.context_data.get("guests_adults")
                self.reservation.guests_children = self.context_data.get("guests_children")
                self.reservation.guests_infants = self.context_data.get("guests_infants")
                self.reservation.base_total = self.context_data.get("base_total")
                self.reservation.price = self.context_data.get("price_total")
                self.reservation.external_id = self.context_data.get("confirmation_code")
                self.reservation.save()
        else:
            guest = Contact.objects.filter(
                email=self.context_data.get("guest_email") or "",
                organization=self.validated_data["organization"],
            )

            if not guest.exists():
                data = dict(
                    email=self.context_data.get("guest_email") or "",
                    organization=self.validated_data["organization"],
                    first_name=self.context_data.get("guest_first_name")
                    or self.context_data.get("guest_name"),
                    last_name=self.context_data.get("guest_last_name") or "",
                    avatar=self.context_data.get("guest_image"),
                    external_id=self.context_data.get("guest_external_id") or "",
                )
                self.guest = Contact.objects.create(**data)
            else:
                self.guest = guest.first()

            status = self.context_data.get("status")
            self.reservation = Reservation.objects.create(
                external_id=self.context_data.get("confirmation_code"),
                confirmation_code=code,
                prop_id=self.get_property_id(),
                start_date=self.context_data.get("start_date"),
                end_date=self.context_data.get("end_date"),
                status=status if status else ReservationStatuses.Accepted.value,
                guests_adults=self.context_data.get("guests_adults"),
                guests_children=self.context_data.get("guests_children"),
                guests_infants=self.context_data.get("guests_infants"),
                guest=self.guest,
                source=Reservation.Sources.Airbnb.value,  # TODO
                base_total=self.context_data.get("base_total"),
                price=self.context_data.get("price_total"),
            )

        thread_id = self.context_data.get("thread_id")
        self.conversation, _ = Conversation.objects.update_or_create(
            reservation=self.reservation,
            defaults=dict(thread_id=thread_id) if thread_id else dict(),
        )

    def get_received_date(self):
        date = self.get_header("Date")
        if date:
            return parsedate_to_datetime(date)
        return None

    def create_message(self):
        message = self.context_data.get("message")
        if message:
            self.message_object = EmailMessage.objects.create(
                html_text=self.validated_data.get("html"),
                text=message,
                outgoing=self.context_data.get("outgoing"),
                conversation=self.conversation,
                recipient=self.validated_data.get("to"),
                sender=self.validated_data.get("from", ""),
                subject=self.validated_data.get("subject"),
                delivery_status=DeliveryStatus.delivered.value,
                date_delivered=self.get_received_date(),
                external_email_id=self.get_header("Message-ID"),
            )
            self.conversation.unread = True
            self.conversation.save()

    def execute(self):  # noqa: C901
        assert self.source is not None, "get_source() must be called first"
        assert self.intent is not None, "get_intent() must be called first"
        if self.source in ["homeaway", "vrbo"]:
            if self.intent == "reservation_canceled":
                pass
            elif self.intent == "new_inquiry":
                self.get_listing_id()

                self.context_data["guest_name"] = self.get_header("X-Inquiry-Name")
                self.context_data["guest_email"] = self.get_header("X-Inquiry-Email")

                message_node = self.soup.find("p", text=re.compile(r"Message from"))
                if message_node:
                    self.context_data["message"] = (
                        message_node.findNext().get_text("\n").strip(" \n")
                    )

                self.context_data["message"] = (
                    self.soup.find("p", text=re.compile(r"Message from"))
                    .findNext("p")
                    .text.strip(" \n")
                )

                self.context_data["guests_adults"] = self.get_header("X-Inquiry-Adults")
                self.context_data["guests_children"] = self.get_header("X-Inquiry-Children")

                date_pattern = "%Y-%m-%d"
                self.context_data["start_date"] = datetime.strptime(
                    self.get_header("X-Inquiry-Arrival"), date_pattern
                ).date()
                self.context_data["end_date"] = datetime.strptime(
                    self.get_header("X-Inquiry-Departure"), date_pattern
                ).date()

                # phone_node = self.soup.find(text=re.compile(r"Traveler phone"))
                # if phone_node:
                #     self.context_data["guest_phone"] = phone_node.findNext().text.strip(" \n")

                self.get_guest()
                self.get_thread_id()
                self.reservation, _ = Reservation.objects.get_or_create(
                    prop_id=self.get_property_id(),
                    start_date=self.context_data.get("start_date"),
                    end_date=self.context_data.get("end_date"),
                    status=ReservationStatuses.Inquiry.value,
                    guest=self.guest,
                    guests_adults=self.context_data.get("guests_adults"),
                    guests_children=self.context_data.get("guests_children") or 0,
                    guests_infants=self.context_data.get("guests_infants") or 0,
                    source=Reservation.Sources.VRBO.value
                    if self.source == "vrbo"
                    else Reservation.Sources.Homeaway.value,  # TODO
                )

                self.conversation, _ = Conversation.objects.get_or_create(
                    reservation=self.reservation, thread_id=self.context_data.get("thread_id")
                )
                self.create_message()

            elif self.intent == "new_reservation":
                pass
            elif self.intent == "new_message":
                self.get_thread_id()
                conversation = Conversation.objects.filter(
                    thread_id=self.context_data.get("thread_id")
                )
                if conversation.exists():
                    self.conversation = conversation[0]

                message_node = (
                    self.soup.find(text=re.compile(r"Respond"))
                    .find_parent("table")
                    .find_parent("table")
                    .findPrevious("table")
                )
                if message_node:
                    self.context_data["message"] = message_node.get_text("\n").strip(" \n")
                    recipient_id = self.get_header("X-Mediated-Recipient-ID")
                    sender_id = self.get_header("X-Mediated-Sender-ID")
                    is_owner = self.get_header("X-Mediated-Recipient-Type") == "OWNER"
                    self.context_data["outgoing"] = is_owner and recipient_id == sender_id
                    self.create_message()

                # reservation_node = self.soup.find(text=re.compile(r"Reservation ID"))
                # if reservation_node:
                #     self.context_data[
                #         "confirmation_code"
                #     ] = reservation_node.findNext().text.strip(" \n")
                #
                # property_node = self.soup.find(text=re.compile(r"Property"))
                # if property_node:
                #     self.context_data["listing_id"] = property_node.findNext().text.strip(" \n")

        elif self.source == "airbnb":
            if self.intent == "reservation_canceled":
                self.get_confirmation_code()
                reservation = Reservation.objects.filter(
                    confirmation_code=self.context_data.get("confirmation_code")
                )
                if reservation.exists():
                    self.reservation = reservation.first()

                    # refund_regex = re.compile(r"Your guest was refunded \$(\d+\.\d+)")
                    # refund_node = self.soup.find("p", text=refund_regex)
                    # if refund_node:
                    #     refund_match = re.compile(refund_regex).findall(refund_node.text)
                    #     if refund_match:
                    #         refund = refund_match[0]
                    #         self.reservation.refunds.create(
                    #             reservation=self.reservation,
                    #             value=Decimal(refund),
                    #             description="Reservation Cancellation"
                    #         )
                    self.reservation.status = ReservationStatuses.Cancelled.value
                    self.reservation.calculate_price()
                    self.reservation.save()

            elif self.intent == "new_inquiry":
                self.get_listing_id()

                # Guest
                guest_node = self.soup.find("p", text=re.compile(r"\d+ verifications?"))
                self.context_data["guest_name"] = guest_node.findPrevious("p").text.strip(" \n")
                email = re.compile(r"Reply-to:.+<(\S+@\S+)>").findall(
                    self.validated_data.get("headers")
                )
                if email:
                    self.context_data["guest_email"] = email[0]

                self.get_message()
                self.get_num_guests()
                self.get_stay_dates()
                self.get_guest()
                self.get_thread_id()
                self.reservation, _ = Reservation.objects.get_or_create(
                    prop_id=self.get_property_id(),
                    start_date=self.context_data.get("start_date"),
                    end_date=self.context_data.get("end_date"),
                    status=ReservationStatuses.Inquiry.value,
                    guest=self.guest,
                    guests_adults=self.context_data.get("guests_adults"),
                    guests_children=self.context_data.get("guests_children"),
                    guests_infants=self.context_data.get("guests_infants"),
                    source=Reservation.Sources.Airbnb.value,  # TODO
                )

                self.conversation, _ = Conversation.objects.get_or_create(
                    reservation=self.reservation, thread_id=self.context_data.get("thread_id")
                )
                self.create_message()

            elif self.intent in ["new_reservation"]:
                self.get_reservation_content()

                self.get_or_create_reservation()

                # Match with 3 common Airbnb fee types
                fee_map = {
                    "cleaning fee": FeeTypes.Cleaning_Fee.value,
                    "service fee": FeeTypes.Service_Fee.value,
                    "security deposit": SecurityDepositTypes.Security_Deposit.value,
                }

                reservation_query = self.reservation.reservationfee_set
                if reservation_query.all().exists():
                    reservation_query.all().delete()

                fees = list()
                for name, value in self.context_data.get("fees"):
                    fee_type = fee_map.get(name.lower(), FeeTypes.Other_Fee.value)
                    name = name if fee_type == FeeTypes.Other_Fee.value else ""
                    fees.append(
                        ReservationFee(
                            **{
                                "name": name,
                                "description": name,
                                "value": value,
                                "fee_tax_type": fee_type,
                                "reservation": self.reservation,
                            }
                        )
                    )

                reservation_query.bulk_create(fees)
                self.create_message()

            elif self.intent == "new_message":
                self.get_message_content()

                self.get_conversation()

                self.create_message()
            elif self.intent == "reservation_request":
                pattern = r"https://www.airbnb.com/rooms/show.+id=(\d+)"
                r = re.compile(pattern)
                m = r.findall(self.validated_data.get("text"))
                if m:
                    self.context_data["listing_id"] = m[0]

                # Guest
                guest_node = self.soup.find("p", text=re.compile(r"\d+ verifications?"))
                self.context_data["guest_name"] = guest_node.findPrevious("p").text.strip(" \n")
                email = re.compile(r"Reply-to:.+<(\S+@\S+)>").findall(
                    self.validated_data.get("headers")
                )
                if email:
                    self.context_data["guest_email"] = email[0]

                code_match = re.compile(r"z/a/([A-Z0-9]{10})").findall(
                    self.validated_data.get("text")
                )
                if code_match:
                    self.context_data["confirmation_code"] = code_match[0]
                self.get_stay_dates()
                self.get_num_guests()
                self.get_message()
                self.context_data["status"] = ReservationStatuses.Request.value
                self.get_or_create_reservation()
                self.create_message()

    def create(self, validated_data):
        # Check if message id exists
        message_id = self.get_header("Message-ID")
        if message_id and Message.objects.filter(external_email_id=message_id).exists():
            raise ValidationError(f"Email with Message-ID={message_id} has already been processed")

        html = validated_data.get("html")
        # Strip obfuscating unicode char
        self.soup = BeautifulSoup(html.replace("\u200c", ""))

        self.get_source()
        self.get_intent()
        self.execute()

        return self.message_object


ParseEmailSerializer._declared_fields["from"] = ParseEmailSerializer._declared_fields["frm"]
del ParseEmailSerializer._declared_fields["frm"]

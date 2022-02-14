from rest_framework import serializers
from rest_framework.fields import SerializerMethodField

from cozmo_common.fields import ChoicesField
from crm.models import Contact
from listings.models import Owner, Reservation
from listings.serializers import PropertyMinimalSerializer
from owners.serializers import OwnerUserSerializer
from send_mail.models import Message


class ContactSearchSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Contact
        fields = (
            "id",
            "first_name",
            "last_name",
            "email",
            "secondary_email",
            "phone",
            "secondary_phone",
            "url",
        )
        extra_kwargs = {"url": {"view_name": "crm_contacts-detail"}}


class PropertySearchSerializer(serializers.HyperlinkedModelSerializer, PropertyMinimalSerializer):
    class Meta(PropertyMinimalSerializer.Meta):
        fields = ("id", "name", "full_address", "cover_image", "url")
        extra_kwargs = {"url": {"view_name": "property:property-detail"}}


class ReservationSearchSerializer(serializers.HyperlinkedModelSerializer):
    serializer_choice_field = ChoicesField
    guest = ContactSearchSerializer()
    prop = PropertySearchSerializer()

    class Meta:
        model = Reservation
        fields = (
            "id",
            "prop",
            "guest",
            "guests_adults",
            "guests_children",
            "guests_infants",
            "start_date",
            "end_date",
            "source",
            "pets",
            "status",
            "dynamic_status",
            "price",
            "base_total",
            "nightly_price",
            "currency",
            "url",
        )
        extra_kwargs = {
            "url": {"view_name": "property:reservations-detail"},
            "price": {"read_only": True}
        }


class ConversationThreadSerializer(serializers.ModelSerializer):
    guest_name = serializers.CharField(source="sender.get_short_name")
    guest_photo = serializers.ImageField(source="sender.avatar")
    reservation = ReservationSearchSerializer()

    class Meta:
        model = Message
        fields = ("id", "guest_name", "guest_photo", "reservation")


class OwnerSearchSerializer(serializers.ModelSerializer):
    name = SerializerMethodField()
    user = OwnerUserSerializer()

    class Meta:
        model = Owner
        fields = (
            "id",
            "name",
            "user"
        )

    def get_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}"


class GenericSearchSerializer(serializers.Serializer):
    properties = PropertySearchSerializer(many=True)
    reservations = ReservationSearchSerializer(many=True)
    conversation_threads = ConversationThreadSerializer(many=True)
    contacts = ContactSearchSerializer(many=True)
    owners = OwnerSearchSerializer(many=True)

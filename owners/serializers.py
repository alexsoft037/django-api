from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.fields import CharField, HiddenField, SerializerMethodField, BooleanField

from accounts.choices import RoleTypes
from accounts.models import Membership, OwnerUser, User
from accounts.serializers import RegisterSerializer
from cozmo_common.fields import DefaultOrganization, ChoicesField
from listings.models import Location, Property
from owners.models import Contract, Owner


class OwnerPropertyLocationSerializer(serializers.ModelSerializer):

    class Meta:
        model = Location
        fields = (
            "country_code",
            "state",
            "city",
            "address",
            "apartment",
            "postal_code",
            "longitude",
            "latitude",
        )


class OwnerPropertySerializer(serializers.ModelSerializer):

    full_address = SerializerMethodField()
    image_url = SerializerMethodField()

    class Meta:
        model = Property
        fields = (
            "id",
            "name",
            "bedrooms",
            "bathrooms",
            "full_address",
            "property_type",
            "rental_type",
            "status",
            "image_url"
        )

    def get_image_url(self, obj):
        return obj.cover_image

    def get_full_address(self, obj):
        return obj.full_address


class OwnerUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = OwnerUser
        fields = (
            "id",
            "first_name",
            "middle_name",
            "last_name",
            "email",
            "phone",
            "username",
        )
        extra_kwargs = {"username": {"write_only": True}}


class ContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contract
        fields = (
            "contract_type",
            "date_signed",
            "date_listed",
            "commission",
            "billing_type",
        )


class OwnerForPropertyListSerializer(serializers.ModelSerializer):

    organization = HiddenField(default=DefaultOrganization())
    user = OwnerUserSerializer(read_only=True)

    first_name = CharField(source="user.first_name", write_only=True, required=False)
    last_name = CharField(source="user.last_name", write_only=True, required=False)
    email = CharField(source="user.email", write_only=True, required=False)
    phone = CharField(source="user.phone", write_only=True, required=False)
    username = CharField(source="user.username", write_only=True, required=False)

    class Meta:
        model = Owner
        fields = (
            "id",
            "user",
            "organization",
            "first_name",
            "last_name",
            "email",
            "phone",
            "username",
        )


class OwnerSerializer(serializers.ModelSerializer):

    properties = OwnerPropertySerializer(many=True, read_only=True, required=False)
    organization = HiddenField(default=DefaultOrganization())
    user = OwnerUserSerializer(read_only=True)

    first_name = CharField(source="user.first_name", write_only=True, required=False)
    last_name = CharField(source="user.last_name", write_only=True, required=False)
    email = CharField(source="user.email", write_only=True, required=False)
    phone = CharField(source="user.phone", write_only=True, required=False)
    username = CharField(source="user.username", write_only=True, required=False)
    contract = ContractSerializer(required=False)

    class Meta:
        model = Owner
        fields = (
            "id",
            "properties",
            "user",
            "organization",
            "notes",
            "first_name",
            "last_name",
            "email",
            "phone",
            "username",
            "contract"
        )

    def create(self, validated_data):
        org = validated_data["organization"]
        with transaction.atomic():
            try:
                user = validated_data["user"]
                owner, _ = User.objects.update_or_create(
                    username=user["username"],
                    defaults=dict(
                        first_name=user["first_name"],
                        last_name=user["last_name"],
                        email=user["email"],
                        phone=user["phone"],
                        role=RoleTypes.property_owner.value,
                    )
                )

                Membership.objects.filter(user=owner, organization=org).get_or_create(
                    user_id=owner.id,
                    organization=org
                    # is_default=True, # TODO bad assumption
                )
                instance = Owner.objects.create(user=owner, organization=org)
                Contract.objects.update_or_create(owner=instance)

            except IntegrityError as e:
                raise ValidationError(e)

        return instance

    def update(self, instance, validated_data):
        contract_data = validated_data.pop("contract", None)
        with transaction.atomic():
            if "user" in validated_data:
                for attr, value in validated_data["user"].items():
                    setattr(instance.user, attr, value)
                instance.user.save()
                del validated_data["user"]

            if contract_data:
                Contract.objects.update_or_create(
                    owner=instance,
                    defaults={
                        "contract_type": contract_data["contract_type"],
                        "date_signed": contract_data["date_signed"],
                        "commission": contract_data["commission"],
                        "billing_type": contract_data["billing_type"],
                        "date_listed": contract_data["date_listed"],
                    }
                )
        return super().update(instance, validated_data)


class OwnerInviteSerializer(RegisterSerializer):
    account_type = ChoicesField(
        choices=User.AllowedTypes.choices(), default=User.AllowedTypes.Owner.value
    )
    organization = HiddenField(default=DefaultOrganization())
    role = ChoicesField(choices=RoleTypes.choices(), default=RoleTypes.property_owner.value)
    invited = BooleanField(default=True)

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
        owner = Owner.objects.create(user=user, organization=request.user.organization)
        Contract.objects.create(owner=owner)
        return user

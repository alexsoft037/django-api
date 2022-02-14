from django.contrib.auth.validators import UnicodeUsernameValidator
from rest_framework import serializers

from .models import HomeAwayAccount, Listing


class ListingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Listing
        fields = ["pk", "name", "image", "address"]


class HomeAwayAccountSerializer(serializers.ModelSerializer):

    password = serializers.CharField(max_length=100, write_only=True)
    listings = ListingSerializer(many=True, read_only=True, source="listing_set")

    class Meta:
        model = HomeAwayAccount
        exclude = ("organization", "session", "data")
        extra_kwargs = {"username": {"validators": [UnicodeUsernameValidator()]}}

    def save(self, **kwargs):
        username = self.validated_data["username"]
        defaults = kwargs.copy()
        account, _ = HomeAwayAccount.objects.update_or_create(username=username, defaults=defaults)
        return account


class Homeaway2faSerializer(serializers.Serializer):
    phone_id = serializers.CharField(max_length=20, required=False)
    method = serializers.ChoiceField({"phone": "phone", "email": "email", "text": "text"})


class HomeawayCodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=20)


class ImportSerializer(serializers.Serializer):

    listings = serializers.ListField(child=serializers.IntegerField(min_value=0), write_only=True)

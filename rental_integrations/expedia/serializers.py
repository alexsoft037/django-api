from rest_framework import serializers

from rental_integrations.serializers import AccountSerializer
from . import models


class ListingSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Listing
        fields = ("pk", "name", "image", "address")


class ExpediaAccountSerializer(AccountSerializer, serializers.ModelSerializer):

    listings = ListingSerializer(source="listing_set", many=True, read_only=True)

    class Meta:
        model = models.ExpediaAccount
        fields = ("id", "user_id", "secret", "listings", "user")


class ImportSerializer(serializers.ModelSerializer):

    secret = serializers.CharField(required=False, write_only=True)
    listings = serializers.PrimaryKeyRelatedField(
        many=True, source="listing_set", queryset=models.Listing.objects.all()
    )

    class Meta:
        model = models.ExpediaAccount
        fields = ("secret", "listings")

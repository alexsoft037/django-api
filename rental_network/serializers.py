from drf_extra_fields.fields import Base64ImageField
from rest_framework import serializers
from rest_framework.serializers import ModelSerializer

from listings.choices import ParkingType, PropertyTypes
from listings.models import Property, Suitability
from rental_network.models import Screenshot


class ScreenshotSerializer(ModelSerializer):
    image = Base64ImageField(max_length=None, use_url=True)

    class Meta:
        model = Screenshot
        fields = ("image", "id", "caption", "job", "date_created")


class BaseSerializer(serializers.Serializer):
    def get_address(self):
        location = self.instance.location
        address_fields = [
            location.address,
            location.city,
            f"{location.state} {location.postal_code}".strip(),
        ]
        return ", ".join([field for field in address_fields if field]).strip()

    def get_photos(self):
        photos = self.instance.image_set.all()
        return photos

    def get_pricing(self):
        pricing_settings = self.instance.pricing_settings
        price = (
            int(pricing_settings.nightly) * 30
            if not pricing_settings.monthly
            else int(pricing_settings.monthly)
        )
        return {"price": str(price), "security_deposit": str(price)}  # set to one month's rent

    class Meta:
        model = Property
        fields = ("location", "photos")


# class CozmoListingToApartmentsAPISerializer(serializers.Serializer):
#     def to_representation(self, instance):
#         data = {
#             "Contact": {
#                 "ContactPreference": 3,
#                 "Email": "ivan@voyajoy.com",
#                 "FirstName": "Ivan",
#                 "LastName": "Thai",
#                 "HideMyPersonalInfo": True,
#                 "PhoneNumber": "4156690356"
#             },
#             "Description": {
#                 "Description": None
#             },
#             "EnablePropertyManagementTools": False
#         }


class CozmoListingToApartmentsSerializer(BaseSerializer):
    # def validate(self, attrs):
    #     """
    #     if apartment or condo, must list unit and floor
    #     must list:
    #      - sqft
    #      - lease_length
    #      - contact_preferene
    #      - role
    #     """
    #     if not attrs.size:
    #         raise ValidationError()
    #     property_type = attrs.property_type
    #     if property_type in [PropertyTypes.Condo.value, PropertyTypes.Apartment.value]:
    #         if not attrs.location.apartment and not attrs.floor:
    #             raise ValidationError()
    #     if not attrs.long_term_rental_settings.lease_length:
    #         raise ValidationError()
    #     return attrs

    def get_manager(self):
        return "I am a Property Manager"

    def get_lease_duration(self):
        # duration = self.instance.long_term_rental_settings.lease_duration
        return "12"

    def to_representation(self, instance):
        # bedrooms = self.instance.bedrooms
        data = {
            "property_type": "Apartment",
            "address": self.get_address(),
            "unit": self.instance.location.apartment.replace("#", ""),
            "photos": self.get_photos(),
            **self.get_amenities(),
            **self.get_pricing(),
            "bedrooms": self.get_bedrooms(),
            "bathrooms": self.get_bathrooms(),
            "sqft": self.instance.size or 1000,
            "floor": self.instance.floor,
            "lease_duration": self.get_lease_duration(),
            "date_available": None,  # set to available now
            "description": self.instance.descriptions.combined_descriptions,  # must be > 0
            "rent_by": self.get_manager(),
            "parking_fee": self.instance.basic_amenities.parking_fee,
            "contact_preference": "Phone & Email",
        }
        return data

    def get_bedrooms(self):
        bedrooms = self.instance.bedrooms
        ret = float(int(bedrooms))
        if ret == 0:
            ret = "Studio"
        elif bedrooms >= 6:
            ret = 6.0
        return str(ret)

    def get_amenities(self):
        amenities = self.instance.basic_amenities
        suitability = self.instance.suitability
        return {
            "amenities": {
                "furnished": True,
                "wheelchair_access": suitability.handicap == Suitability.SuitabilityProvided.Yes,
                "parking": amenities.street_parking,
                "laundry": amenities.washer or amenities.dryer or amenities.laundry,
                "pets": suitability.pets == Suitability.SuitabilityProvided.Yes,
                "smoking": suitability.smoking == Suitability.SuitabilityProvided.Yes,
            },
            "additional_amenities": [],
        }

    def get_bathrooms(self):
        bathrooms = self.instance.bathrooms

        if bathrooms >= 6.5:
            return 6.5
        return float(bathrooms)

    class Meta:
        model = Property
        fields = ("location", "photos")


class CozmoListingToZillowSerializer(BaseSerializer):
    def validate(self, attrs):
        return attrs

    def get_property_type(self):
        CONDO_APARTMENT = "Condo / Apartment Unit"
        HOUSE = "House"
        TOWNHOUSE = "Townhouse"
        # ENTIRE_APT_COM = "Entire Apartment Community"
        property_type = self.instance.property_type
        types = {
            PropertyTypes.Apartment.value: CONDO_APARTMENT,
            PropertyTypes.House.value: HOUSE,
            PropertyTypes.Condo.value: CONDO_APARTMENT,
            PropertyTypes.Townhouse.value: TOWNHOUSE,
        }
        return types.get(property_type, HOUSE)

    def get_lease_duration(self):
        return "Sublet/temporary"

    def get_manager(self):
        return "Management Company / Broker"

    def to_representation(self, instance):
        """

        :param instance:
        :return:
        """

        bedrooms = self.instance.bedrooms
        data = {
            "property_type": self.get_property_type(),
            "address": self.get_address(),
            "unit": self.instance.location.apartment,
            "photos": self.get_photos(),
            **self.get_amenities(),
            **self.get_pricing(),
            "bedrooms": int(bedrooms) if int(bedrooms) > 0 else "Studio",
            "bathrooms": self.get_bathrooms(),
            "sqft": self.instance.size or 1000,
            "lease_duration": self.get_lease_duration(),
            "lease_terms": "",
            "date_available": None,  # set to available now
            "description": self.instance.descriptions.combined_descriptions,  # must be > 0
            "rent_by": self.get_manager(),
        }
        return data

    def get_bathrooms(self):
        bathrooms = self.instance.bathrooms
        ret = bathrooms
        if bathrooms % 1 == 0:
            ret = int(bathrooms)
        elif bathrooms >= 5:
            ret = "5+"
        return str(ret)

    def get_amenities(self):
        amenities = self.instance.basic_amenities
        suitability = self.instance.suitability
        return {
            "amenities": {
                "ac": amenities.ac,
                "balcony": amenities.patio_or_balcony,
                "furnished": amenities.furnished,
                "hardwood_floor": amenities.hardwood_flooring,
                "wheelchair_access": suitability.handicap == Suitability.SuitabilityProvided.Yes,
                "garage_parking": amenities.parking_type == ParkingType.garage.value,
                "off_street_parking": not amenities.street_parking
                and amenities.parking_type != ParkingType.none.value,
                "laundry": amenities.washer or amenities.dryer or amenities.laundry,
                "pets": suitability.pets == Suitability.SuitabilityProvided.Yes,
            },
            "additional_amenities": [],
        }

from collections import defaultdict
from enum import Enum

from app_marketplace.choices import AirbnbApprovalStatus
from listings import choices as cozmo_choices
from listings.choices import CalculationMethod, FeeTypes
from listings.models import Room
from rental_integrations.airbnb.constants import ApprovalNotes
from rental_integrations.choices import ListingApprovalStatus, ListingRequirements
from . import choices

raw_approval_notes_to_cozmo = {
    ApprovalNotes.not_enough_photos.value: ListingRequirements.photos,
    ApprovalNotes.not_enough_description.value: ListingRequirements.description,
    ApprovalNotes.not_enough_amenities.value: ListingRequirements.amenities,
    ApprovalNotes.not_enough_hd_photos.value: ListingRequirements.hd_photos,
    ApprovalNotes.no_permit.value: ListingRequirements.permits,
}

approval_status_to_cozmo = {
    AirbnbApprovalStatus.new: ListingApprovalStatus.new,
    AirbnbApprovalStatus.ready_for_review: ListingApprovalStatus.ready_for_review,
    AirbnbApprovalStatus.approved: ListingApprovalStatus.approved,
    AirbnbApprovalStatus.rejected: ListingApprovalStatus.rejected,
}

approval_status_to_cozmo_value = {k.value: v.value for k, v in approval_status_to_cozmo.items()}

cozmo_beds = {
    Room.Beds.King: choices.BedType.king_bed,
    Room.Beds.Queen: choices.BedType.queen_bed,
    Room.Beds.Double: choices.BedType.double_bed,
    Room.Beds.Single: choices.BedType.single_bed,
    Room.Beds.Sofa: choices.BedType.sofa_bed,
    Room.Beds.Couch: choices.BedType.couch,
    Room.Beds.Air_Mattress: choices.BedType.air_mattress,
    Room.Beds.Bunk: choices.BedType.bunk_bed,
    Room.Beds.Floor_Mattress: choices.BedType.floor_mattress,
    Room.Beds.Toddler: choices.BedType.toddler_bed,
    Room.Beds.Crib: choices.BedType.crib,
    Room.Beds.Water: choices.BedType.water_bed,
    Room.Beds.Hammock: choices.BedType.hammock,
}

cozmo_to_airbnb_bed_names = {k.value: v.value for k, v in cozmo_beds.items()}

airbnb_beds = {v: k for k, v in cozmo_beds.items()}

airbnb_cancellation_policy = {
    choices.CancellationPolicy.flexible: cozmo_choices.CancellationPolicy.Relaxed.name,
    choices.CancellationPolicy.moderate: cozmo_choices.CancellationPolicy.Flexible.name,
    choices.CancellationPolicy.strict: cozmo_choices.CancellationPolicy.Moderate.name,
    choices.CancellationPolicy.strict_14_with_grace_period: cozmo_choices.CancellationPolicy.Firm.name,  # noqa E501
    choices.CancellationPolicy.super_strict_30: cozmo_choices.CancellationPolicy.Strict.name,
    choices.CancellationPolicy.super_strict_60: cozmo_choices.CancellationPolicy.Super_Strict.name,
    choices.CancellationPolicy.long_term: cozmo_choices.CancellationPolicy.Long_Term.name,
    choices.CancellationPolicy.long_term_grace_period: cozmo_choices.CancellationPolicy.Long_Term.name,  # noqa E501
}

airbnb_fees = {
    choices.FeeType.resort_fee: cozmo_choices.FeeTypes.Resort_Fee.pretty_name,
    choices.FeeType.management_fee: cozmo_choices.FeeTypes.Other_Fee.pretty_name,
    choices.FeeType.community_fee: cozmo_choices.FeeTypes.Community_Fee.pretty_name,
    choices.FeeType.linen_fee: cozmo_choices.FeeTypes.Linen_Fee.pretty_name,
}

cozmo_cancellation_policy = defaultdict(
    lambda: None,
    {
        cozmo_choices.CancellationPolicy[cozmo].value: airbnb.value
        for airbnb, cozmo in airbnb_cancellation_policy.items()
    },
)


class _class_getitem(type):
    def __getitem__(cls, item):
        return cls._get_item(item)


class cozmo_property_type(metaclass=_class_getitem):
    @classmethod
    def _get_item(cls, item) -> str:
        try:
            if not isinstance(item, Enum):
                item = cozmo_choices.PropertyTypes(item)
            airbnb_type = choices.PropertyType[item.name.lower()].value
        except (ValueError, KeyError):
            airbnb_type = None
            # raise Exception(f"Property type mapping does not exist for airbnb type: {item}")
        return airbnb_type


airbnb_property_type = {
    choices.PropertyType.aparthotel: cozmo_choices.PropertyTypes.Aparthotel,
    choices.PropertyType.apartment: cozmo_choices.PropertyTypes.Apartment,
    choices.PropertyType.barn: cozmo_choices.PropertyTypes.Barn,
    choices.PropertyType.bed_and_breakfast: cozmo_choices.PropertyTypes.Bed_and_Breakfast,
    choices.PropertyType.boat: cozmo_choices.PropertyTypes.Boat,
    choices.PropertyType.boutique_hotel: cozmo_choices.PropertyTypes.Boutique_Hotel,
    choices.PropertyType.bungalow: cozmo_choices.PropertyTypes.Bungalow,
    choices.PropertyType.cabin: cozmo_choices.PropertyTypes.Cabin,
    choices.PropertyType.campsite: cozmo_choices.PropertyTypes.Campsite,
    choices.PropertyType.casa_particular: cozmo_choices.PropertyTypes.Casa_Particular,
    choices.PropertyType.castle: cozmo_choices.PropertyTypes.Castle,
    choices.PropertyType.cave: cozmo_choices.PropertyTypes.Cave,
    choices.PropertyType.chalet: cozmo_choices.PropertyTypes.Chalet,
    choices.PropertyType.condominium: cozmo_choices.PropertyTypes.Condo,
    choices.PropertyType.cottage: cozmo_choices.PropertyTypes.Cottage,
    choices.PropertyType.cycladic_house: cozmo_choices.PropertyTypes.Cycladic_House,
    choices.PropertyType.dammuso: cozmo_choices.PropertyTypes.Dammuso,
    choices.PropertyType.dome_house: cozmo_choices.PropertyTypes.Dome_House,
    choices.PropertyType.earthhouse: cozmo_choices.PropertyTypes.Earth_House,
    choices.PropertyType.farm_stay: cozmo_choices.PropertyTypes.Farmhouse,
    choices.PropertyType.guest_suite: cozmo_choices.PropertyTypes.Guest_Suite,
    choices.PropertyType.guesthouse: cozmo_choices.PropertyTypes.Guesthouse,
    choices.PropertyType.heritage_hotel: cozmo_choices.PropertyTypes.Heritage_Hotel,
    choices.PropertyType.hostel: cozmo_choices.PropertyTypes.Hostel,
    choices.PropertyType.hotel: cozmo_choices.PropertyTypes.Hotel,
    choices.PropertyType.house: cozmo_choices.PropertyTypes.House,
    choices.PropertyType.houseboat: cozmo_choices.PropertyTypes.Houseboat,
    choices.PropertyType.hut: cozmo_choices.PropertyTypes.Hut,
    choices.PropertyType.igloo: cozmo_choices.PropertyTypes.Igloo,
    choices.PropertyType.island: cozmo_choices.PropertyTypes.Island,
    choices.PropertyType.lighthouse: cozmo_choices.PropertyTypes.Light_House,
    choices.PropertyType.lodge: cozmo_choices.PropertyTypes.Lodge,
    choices.PropertyType.loft: cozmo_choices.PropertyTypes.Loft,
    choices.PropertyType.minsu: cozmo_choices.PropertyTypes.Minsu,
    choices.PropertyType.pension: cozmo_choices.PropertyTypes.Pension,
    choices.PropertyType.plane: cozmo_choices.PropertyTypes.Plane,
    choices.PropertyType.resort: cozmo_choices.PropertyTypes.Resort,
    choices.PropertyType.rv: cozmo_choices.PropertyTypes.Mobile_Home,
    choices.PropertyType.ryokan: cozmo_choices.PropertyTypes.Ryokan,
    choices.PropertyType.serviced_apartment: cozmo_choices.PropertyTypes.Serviced_Apartment,
    choices.PropertyType.shepherds_hut: cozmo_choices.PropertyTypes.Shepherds_Hut,
    choices.PropertyType.tent: cozmo_choices.PropertyTypes.Tent,
    choices.PropertyType.tiny_house: cozmo_choices.PropertyTypes.Tiny_House,
    choices.PropertyType.tipi: cozmo_choices.PropertyTypes.Tipi,
    choices.PropertyType.townhouse: cozmo_choices.PropertyTypes.Townhouse,
    choices.PropertyType.train: cozmo_choices.PropertyTypes.Train,
    choices.PropertyType.treehouse: cozmo_choices.PropertyTypes.Treehouse,
    choices.PropertyType.trullo: cozmo_choices.PropertyTypes.Trullo,
    choices.PropertyType.villa: cozmo_choices.PropertyTypes.Villa,
    choices.PropertyType.windmill: cozmo_choices.PropertyTypes.Windmill,
    choices.PropertyType.yurt: cozmo_choices.PropertyTypes.Yurt,
}


cozmo_airbnb_property_type = {v.value: k.value for k, v in airbnb_property_type.items()}

airbnb_rental_type = {
    choices.RoomType.entire_home: cozmo_choices.Rentals.Entire_Home.pretty_name,
    choices.RoomType.private_room: cozmo_choices.Rentals.Private.pretty_name,
    choices.RoomType.shared_room: cozmo_choices.Rentals.Shared.pretty_name,
}


cozmo_rental_type = {
    cozmo_choices.Rentals.Entire_Home.value: choices.RoomType.entire_home.value,
    cozmo_choices.Rentals.Other.value: choices.RoomType.private_room.value,
    cozmo_choices.Rentals.Private.value: choices.RoomType.private_room.value,
    cozmo_choices.Rentals.Shared.value: choices.RoomType.shared_room.value,
}


airbnb_reservation_status = {
    choices.ReservationStatus.new: cozmo_choices.ReservationStatuses.Inquiry.value,
    choices.ReservationStatus.accept: cozmo_choices.ReservationStatuses.Accepted.value,
    choices.ReservationStatus.deny: cozmo_choices.ReservationStatuses.Declined.value,
    choices.ReservationStatus.pending: cozmo_choices.ReservationStatuses.Inquiry_Blocked.value,
    choices.ReservationStatus.timeout: cozmo_choices.ReservationStatuses.Declined.value,
    choices.ReservationStatus.pending_voided: cozmo_choices.ReservationStatuses.Declined.value,
    choices.ReservationStatus.pending_payment: cozmo_choices.ReservationStatuses.Inquiry_Blocked.value,  # noqa: E501
    choices.ReservationStatus.cancelled_by_admin: cozmo_choices.ReservationStatuses.Cancelled.value,  # noqa: E501
    choices.ReservationStatus.cancelled_by_host: cozmo_choices.ReservationStatuses.Cancelled.value,
    choices.ReservationStatus.cancelled_by_guest: cozmo_choices.ReservationStatuses.Cancelled.value,  # noqa: E501
    choices.ReservationStatus.at_checkpoint: cozmo_choices.ReservationStatuses.Inquiry_Blocked.value,  # noqa: E501
    choices.ReservationStatus.checkpoint_voided: cozmo_choices.ReservationStatuses.Declined.value,
}

airbnb_reservation_status_to_cozmo = {
    choices.ReservationStatus.new: cozmo_choices.ReservationStatuses.Inquiry,
    choices.ReservationStatus.accept: cozmo_choices.ReservationStatuses.Accepted,
    choices.ReservationStatus.deny: cozmo_choices.ReservationStatuses.Declined,
    choices.ReservationStatus.pending: cozmo_choices.ReservationStatuses.Inquiry_Blocked,
    choices.ReservationStatus.timeout: cozmo_choices.ReservationStatuses.Declined,
    choices.ReservationStatus.pending_voided: cozmo_choices.ReservationStatuses.Declined,
    choices.ReservationStatus.pending_payment: cozmo_choices.ReservationStatuses.Inquiry_Blocked,  # noqa: E501
    choices.ReservationStatus.cancelled_by_admin: cozmo_choices.ReservationStatuses.Cancelled,  # noqa: E501
    choices.ReservationStatus.cancelled_by_host: cozmo_choices.ReservationStatuses.Cancelled,
    choices.ReservationStatus.cancelled_by_guest: cozmo_choices.ReservationStatuses.Cancelled,  # noqa: E501
    choices.ReservationStatus.at_checkpoint: cozmo_choices.ReservationStatuses.Inquiry_Blocked,  # noqa: E501
    choices.ReservationStatus.checkpoint_voided: cozmo_choices.ReservationStatuses.Declined,
}


airbnb_reservation_status_str_to_val = defaultdict(
    lambda: None,
    {
        choices.ReservationStatus[airbnb.name]: cozmo
        for airbnb, cozmo in airbnb_reservation_status.items()
    },
)


class type_to_group(metaclass=_class_getitem):

    _mapping = {
        choices.PropertyTypeGroup.apartments: (
            choices.PropertyType.apartment.value,
            choices.PropertyType.condominium.value,
            choices.PropertyType.loft.value,
            choices.PropertyType.serviced_apartment.value,
            choices.PropertyType.casa_particular.value,
        ),
        choices.PropertyTypeGroup.bnb: (
            choices.PropertyType.bed_and_breakfast.value,
            choices.PropertyType.farm_stay.value,
            choices.PropertyType.lodge.value,
            choices.PropertyType.casa_particular.value,
            choices.PropertyType.minsu.value,
            choices.PropertyType.ryokan.value,
        ),
        choices.PropertyTypeGroup.boutique_hotels_and_more: (
            choices.PropertyType.boutique_hotel.value,
            choices.PropertyType.aparthotel.value,
            choices.PropertyType.hostel.value,
            choices.PropertyType.hotel.value,
            choices.PropertyType.lodge.value,
            choices.PropertyType.resort.value,
            choices.PropertyType.serviced_apartment.value,
            choices.PropertyType.heritage_hotel.value,
        ),
        choices.PropertyTypeGroup.houses: (
            choices.PropertyType.bungalow.value,
            choices.PropertyType.cabin.value,
            choices.PropertyType.chalet.value,
            choices.PropertyType.cottage.value,
            choices.PropertyType.dome_house.value,
            choices.PropertyType.earthhouse.value,
            choices.PropertyType.farm_stay.value,
            choices.PropertyType.house.value,
            choices.PropertyType.houseboat.value,
            choices.PropertyType.hut.value,
            choices.PropertyType.lighthouse.value,
            choices.PropertyType.tiny_house.value,
            choices.PropertyType.townhouse.value,
            choices.PropertyType.villa.value,
            choices.PropertyType.casa_particular.value,
            choices.PropertyType.cycladic_house.value,
            choices.PropertyType.dammuso.value,
            choices.PropertyType.shepherds_hut.value,
            choices.PropertyType.trullo.value,
            choices.PropertyType.pension.value,
        ),
        choices.PropertyTypeGroup.secondary_units: (
            choices.PropertyType.guesthouse.value,
            choices.PropertyType.guest_suite.value,
            choices.PropertyType.farm_stay.value,
        ),
        choices.PropertyTypeGroup.unique_homes: (
            choices.PropertyType.barn.value,
            choices.PropertyType.boat.value,
            choices.PropertyType.rv.value,
            choices.PropertyType.campsite.value,
            choices.PropertyType.castle.value,
            choices.PropertyType.cave.value,
            choices.PropertyType.dome_house.value,
            choices.PropertyType.earthhouse.value,
            choices.PropertyType.farm_stay.value,
            choices.PropertyType.houseboat.value,
            choices.PropertyType.hut.value,
            choices.PropertyType.igloo.value,
            choices.PropertyType.island.value,
            choices.PropertyType.lighthouse.value,
            choices.PropertyType.plane.value,
            choices.PropertyType.tent.value,
            choices.PropertyType.tiny_house.value,
            choices.PropertyType.tipi.value,
            choices.PropertyType.train.value,
            choices.PropertyType.treehouse.value,
            choices.PropertyType.windmill.value,
            choices.PropertyType.yurt.value,
            choices.PropertyType.pension.value,
            choices.PropertyType.shepherds_hut.value,
        ),
    }

    @classmethod
    def _get_item(cls, item):
        for group, items in cls._mapping.items():
            if item in items:
                return group.value
        return None


class cozmo_to_airbnb_fee_types(metaclass=_class_getitem):

    _mapping = {
        choices.FeeType.community_fee: (FeeTypes.Community_Fee.value,),
        choices.FeeType.linen_fee: (
            FeeTypes.Towel_Fee.value,
            FeeTypes.Linen_Fee.value,
            FeeTypes.Cleaning_Fee.value,
        ),
        choices.FeeType.management_fee: (
            FeeTypes.Booking_Fee.value,
            FeeTypes.Service_Fee.value,
            FeeTypes.Platform_Fee.value,
        ),
        choices.FeeType.resort_fee: (
            FeeTypes.Resort_Fee.value,
            FeeTypes.Electricity_Fee.value,
            FeeTypes.Damage_Protection_Insurance_Fee.value,
            FeeTypes.Other_Fee.value,
        ),
    }

    @classmethod
    def _get_item(cls, item):
        for group, items in cls._mapping.items():
            if item in items:
                return group.value
        return None


class cozmo_to_airbnb_calculation_methods(metaclass=_class_getitem):

    _mapping = {
        choices.AmountType.percent: (
            CalculationMethod.Per_Stay_Percent.value,
            CalculationMethod.Per_Stay_Only_Rates_Percent.value,
            CalculationMethod.Per_Stay_No_Taxes_Percent.value,
        ),
        choices.AmountType.flat: (
            CalculationMethod.Daily.value,
            CalculationMethod.Per_Stay.value,
            CalculationMethod.Per_Person_Per_Day.value,
            CalculationMethod.Per_Person_Per_Stay.value,
        ),
    }

    @classmethod
    def _get_item(cls, item):
        for group, items in cls._mapping.items():
            if item in items:
                return group.value
        return None


class Mapper(metaclass=_class_getitem):
    def __init__(self, mapping):
        self.mapping = mapping
        self.name_mapping = {k.name: v.name for k, v in mapping.items()}
        self.value_mapping = {k.value: v.value for k, v in mapping.items()}

    def get_by_name(self, name, reverse=False):
        name_dict = (
            self.name_mapping if not reverse else {v: k for k, v in self.name_mapping.items()}
        )
        return name_dict.get(name, None)

    def get_by_name_to_pretty(self, name, reverse=False):
        name_to_pretty = {k: v.pretty_name for k, v in self.mapping.items()}
        name_dict = (
            name_to_pretty if not reverse else {v: k.pretty_name for k, v in self.mapping.items()}
        )
        return name_dict.get(name, None)

    def get_by_value(self, value, reverse=False):
        value_dict = (
            self.value_mapping if not reverse else {v: k for k, v in self.value_mapping.items()}
        )
        return value_dict.get(value, None)


airbnb_to_cozmo_fee_types = Mapper(
    {
        choices.FeeType.community_fee: FeeTypes.Community_Fee,
        choices.FeeType.linen_fee: FeeTypes.Linen_Fee,
        choices.FeeType.management_fee: FeeTypes.Service_Fee,
        choices.FeeType.resort_fee: FeeTypes.Resort_Fee,
    }
)

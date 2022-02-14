from collections import defaultdict

from listings.choices import PropertyTypes

Apartment = 3
BedAndBreakfast = 4
Cabin = 5
Campground = 6
Chalet = 7
Condominium = 8
Cruise = 12
Ferry = 14
GuestFarm = 15
GuestHouse = 16
HolidayResort = 18
Hostel = 19
Hotel = 20
Inn = 21
Lodge = 22
MeetingResort = 23
MobileHome = 25
Monastery = 26
Motel = 27
Ranch = 28
ResidentialApartment = 29
Resort = 30
SailingShip = 31
SelfCateringAccommodation = 32
Tent = 33
VacationHome = 34
Villa = 35
WildlifeReserve = 36
Castle = 37
Pension = 40
Boatel = 44
Boutique = 45
Studio = 46
RecreationalVehiclePark = 50
CharmHotel = 51
Manor = 52
ApartHotel = 5000
Riad = 5001
Ryokan = 5002
LoveHotel = 5003
Homestay = 5004
JapaneseBusinessHotel = 5005
HolidayHome = 5006
CountryHouse = 5007
CapsuleHotel = 5008


cozmo_to_booking = defaultdict(
    lambda: Apartment,
    {
        PropertyTypes.Apartment.value: Apartment,
        PropertyTypes.Bed_and_Breakfast.value: BedAndBreakfast,
        PropertyTypes.Boat.value: Cruise,
        PropertyTypes.Bungalow.value: Cabin,
        PropertyTypes.Cabin.value: Cabin,
        PropertyTypes.Camper_Rv.value: Campground,
        PropertyTypes.Castle.value: Castle,
        PropertyTypes.Cave.value: CountryHouse,
        PropertyTypes.Chalet.value: Chalet,
        PropertyTypes.Condo.value: Condominium,
        PropertyTypes.Cottage.value: CountryHouse,
        PropertyTypes.Dorm.value: None,
        PropertyTypes.Earth_House.value: CountryHouse,
        PropertyTypes.Estate.value: HolidayResort,
        PropertyTypes.Farmhouse.value: GuestFarm,
        PropertyTypes.Guest_Suite.value: Pension,
        PropertyTypes.Guesthouse.value: GuestHouse,
        PropertyTypes.Hotel.value: Hotel,
        PropertyTypes.House.value: Pension,
        PropertyTypes.Houseboat.value: SailingShip,
        PropertyTypes.Hut.value: Lodge,
        PropertyTypes.Igloo.value: Lodge,
        PropertyTypes.In_Law.value: Inn,
        PropertyTypes.Inn.value: Inn,
        PropertyTypes.Island.value: CountryHouse,
        PropertyTypes.Loft.value: Studio,
        PropertyTypes.Mobile_Home.value: MobileHome,
        PropertyTypes.Other.value: None,
        PropertyTypes.Plane.value: None,
        PropertyTypes.Ski_Inn.value: Inn,
        PropertyTypes.Studio.value: Studio,
        PropertyTypes.Tent.value: Tent,
        PropertyTypes.Tipi.value: Tent,
        PropertyTypes.Townhouse.value: ResidentialApartment,
        PropertyTypes.Train.value: None,
        PropertyTypes.Treehouse.value: GuestHouse,
        PropertyTypes.Vacation_Home.value: VacationHome,
        PropertyTypes.Villa.value: Villa,
        PropertyTypes.Yacht.value: SailingShip,
        PropertyTypes.Yurt.value: Tent,
    },
)


booking_to_cozmo = defaultdict(
    lambda: PropertyTypes.Apartment.value,
    {
        Apartment: PropertyTypes.Apartment.value,
        BedAndBreakfast: PropertyTypes.Bed_and_Breakfast.value,
        Cabin: PropertyTypes.Cabin.value,
        Campground: PropertyTypes.Camper_Rv.value,
        Chalet: PropertyTypes.Chalet.value,
        Condominium: PropertyTypes.Condo.value,
        Cruise: PropertyTypes.Boat.value,
        Ferry: PropertyTypes.Boat.value,
        GuestFarm: PropertyTypes.Farmhouse.value,
        GuestHouse: PropertyTypes.Guesthouse.value,
        HolidayResort: PropertyTypes.Estate.value,
        Hostel: None,
        Hotel: PropertyTypes.Hotel.value,
        Inn: PropertyTypes.Inn.value,
        Lodge: PropertyTypes.Hut,
        MeetingResort: None,
        MobileHome: PropertyTypes.Mobile_Home.value,
        Monastery: None,
        Motel: None,
        Ranch: PropertyTypes.Farmhouse,
        ResidentialApartment: PropertyTypes.Townhouse.value,
        Resort: None,
        SailingShip: PropertyTypes.Houseboat.value,
        SelfCateringAccommodation: None,
        Tent: PropertyTypes.Tent.value,
        VacationHome: PropertyTypes.Vacation_Home.value,
        Villa: PropertyTypes.Villa.value,
        WildlifeReserve: None,
        Castle: PropertyTypes.Castle.value,
        Pension: PropertyTypes.House.value,
        Boatel: PropertyTypes.Boat.value,
        Boutique: None,
        Studio: PropertyTypes.Studio.value,
        RecreationalVehiclePark: PropertyTypes.Camper_Rv.value,
        CharmHotel: None,
        Manor: None,
        ApartHotel: None,
        Riad: None,
        Ryokan: None,
        LoveHotel: None,
        Homestay: None,
        JapaneseBusinessHotel: None,
        HolidayHome: None,
        CountryHouse: PropertyTypes.Cottage.value,
        CapsuleHotel: None,
    },
)

from listings.choices import PropertyTypes

property_types_map = {
    "Townhouse": PropertyTypes.Townhouse.pretty_name,
    "Cabin / Bungalow": PropertyTypes.Cabin.pretty_name,
    "Duplex": PropertyTypes.House.pretty_name,
    "Lodge": PropertyTypes.Vacation_Home.pretty_name,
    "Triplex": PropertyTypes.House.pretty_name,
    "Condominium": PropertyTypes.Condo.pretty_name,
    "House": PropertyTypes.House.pretty_name,
}

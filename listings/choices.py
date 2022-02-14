from enum import unique

from iso3166 import countries_by_alpha2

from cozmo_common.enums import IntChoicesEnum, StrChoicesEnum


class CalculationMethod(StrChoicesEnum):
    Daily = "DA"
    Per_Stay = "PS"
    Per_Person_Per_Day = "PD"
    Per_Person_Per_Stay = "3P"
    Per_Stay_Percent = "PP"
    Per_Stay_Only_Rates_Percent = "OR"
    Per_Stay_No_Taxes_Percent = "NT"


_currencySymbols = {"USD": "$", "EUR": "€", "GBP": "£"}


class CancellationPolicy(StrChoicesEnum):
    Full = "EA"
    Relaxed = "OK"
    Flexible = "FA"
    Moderate = "RI"
    Firm = "FI"
    Strict = "ST"
    Super_Strict = "SS"
    Long_Term = "LT"
    No_Refunds = "NR"
    Unknown = "UN"


CountryCode = StrChoicesEnum(
    "CountryCode", {code.upper(): code.upper() for code in sorted(countries_by_alpha2.keys())}
)


class Currencies(StrChoicesEnum):
    """Currencies data taken from https://www.iso.org/iso-4217-currency-codes.html"""

    AFN = "AFN"
    DZD = "DZD"
    ARS = "ARS"
    AMD = "AMD"
    AWG = "AWG"
    AUD = "AUD"
    AZN = "AZN"
    BSD = "BSD"
    BHD = "BHD"
    THB = "THB"
    PAB = "PAB"
    BBD = "BBD"
    BYN = "BYN"
    BZD = "BZD"
    BMD = "BMD"
    BOB = "BOB"
    VEF = "VEF"
    BRL = "BRL"
    BND = "BND"
    BGN = "BGN"
    BIF = "BIF"
    CVE = "CVE"
    CAD = "CAD"
    KYD = "KYD"
    CLP = "CLP"
    COP = "COP"
    KMF = "KMF"
    CDF = "CDF"
    BAM = "BAM"
    NIO = "NIO"
    CRC = "CRC"
    CUP = "CUP"
    CZK = "CZK"
    GMD = "GMD"
    DKK = "DKK"
    MKD = "MKD"
    DJF = "DJF"
    STN = "STN"
    DOP = "DOP"
    VND = "VND"
    XCD = "XCD"
    EGP = "EGP"
    SVC = "SVC"
    ETB = "ETB"
    EUR = "EUR"
    FKP = "FKP"
    FJD = "FJD"
    HUF = "HUF"
    GHS = "GHS"
    GIP = "GIP"
    HTG = "HTG"
    PYG = "PYG"
    GNF = "GNF"
    GYD = "GYD"
    HKD = "HKD"
    UAH = "UAH"
    ISK = "ISK"
    INR = "INR"
    IRR = "IRR"
    IQD = "IQD"
    JMD = "JMD"
    JOD = "JOD"
    KES = "KES"
    PGK = "PGK"
    HRK = "HRK"
    KWD = "KWD"
    AOA = "AOA"
    MMK = "MMK"
    LAK = "LAK"
    GEL = "GEL"
    LBP = "LBP"
    ALL = "ALL"
    HNL = "HNL"
    SLL = "SLL"
    LRD = "LRD"
    LYD = "LYD"
    SZL = "SZL"
    LSL = "LSL"
    MGA = "MGA"
    MWK = "MWK"
    MYR = "MYR"
    MUR = "MUR"
    MXN = "MXN"
    MDL = "MDL"
    MAD = "MAD"
    MZN = "MZN"
    BOV = "BOV"
    NGN = "NGN"
    ERN = "ERN"
    NAD = "NAD"
    NPR = "NPR"
    ANG = "ANG"
    ILS = "ILS"
    TWD = "TWD"
    NZD = "NZD"
    BTN = "BTN"
    KPW = "KPW"
    NOK = "NOK"
    MRU = "MRU"
    PKR = "PKR"
    MOP = "MOP"
    TOP = "TOP"
    CUC = "CUC"
    UYU = "UYU"
    PHP = "PHP"
    GBP = "GBP"
    BWP = "BWP"
    QAR = "QAR"
    GTQ = "GTQ"
    ZAR = "ZAR"
    OMR = "OMR"
    KHR = "KHR"
    RON = "RON"
    MVR = "MVR"
    IDR = "IDR"
    RUB = "RUB"
    RWF = "RWF"
    SHP = "SHP"
    SAR = "SAR"
    RSD = "RSD"
    SCR = "SCR"
    SGD = "SGD"
    PEN = "PEN"
    SBD = "SBD"
    KGS = "KGS"
    SOS = "SOS"
    TJS = "TJS"
    SSP = "SSP"
    LKR = "LKR"
    XSU = "XSU"
    SDG = "SDG"
    SRD = "SRD"
    SEK = "SEK"
    CHF = "CHF"
    SYP = "SYP"
    BDT = "BDT"
    WST = "WST"
    TZS = "TZS"
    KZT = "KZT"
    TTD = "TTD"
    MNT = "MNT"
    TND = "TND"
    TRY = "TRY"
    TMT = "TMT"
    AED = "AED"
    USD = "USD"
    UGX = "UGX"
    CLF = "CLF"
    COU = "COU"
    UZS = "UZS"
    VUV = "VUV"
    KRW = "KRW"
    YER = "YER"
    JPY = "JPY"
    CNY = "CNY"
    ZMW = "ZMW"
    ZWL = "ZWL"
    PLN = "PLN"

    @property
    def symbol(self):
        return _currencySymbols.get(self.value, "")


class FeeTypes(StrChoicesEnum):
    Electricity_Fee = "FEL"
    Towel_Fee = "FTW"
    Damage_Protection_Insurance_Fee = "FDP"
    Booking_Fee = "FBO"
    Service_Fee = "FSE"
    Resort_Fee = "FRE"
    Community_Fee = "FCO"
    Linen_Fee = "FLE"
    Platform_Fee = "PFM"
    Cleaning_Fee = "CLN"
    Other_Fee = "FOT"


class SecurityDepositTypes(StrChoicesEnum):
    Security_Deposit = "FSD"


class PaymentStatusType(IntChoicesEnum):
    scheduled = 1
    open = 2
    refunded = 3
    partially_refunded = 4
    completed = 5
    cancelled = 6
    reversed = 7
    disputed = 8


class PaymentSource(IntChoicesEnum):
    guest = 1
    host = 2
    platform = 3


class PaymentMethodType(IntChoicesEnum):
    credit_card = 0
    check = 1
    cash = 2
    money_order = 3
    bank_transfer = 4
    paypal = 5
    venmo = 6


class LineItemType(IntChoicesEnum):
    fee = 1
    tax = 2
    refundable_deposit = 3


class FeeType(IntChoicesEnum):
    host = 1
    renter = 2


class TaxTypes(StrChoicesEnum):
    Local_Tax = "TLC"
    Tourist_Tax = "TTR"
    VAT = "TVA"
    Hotel_Tax = "THO"
    Other_Tax = "TOT"


class Rentals(StrChoicesEnum):
    Entire_Home = "RE"
    Other = "OT"
    Private = "RP"
    Shared = "RS"


class ReservationStatuses(IntChoicesEnum):
    Accepted = 1
    Cancelled = 2
    Declined = 3
    Inquiry = 4
    Inquiry_Blocked = 5
    Request = 6


class PropertyStatuses(IntChoicesEnum):
    Active = 1
    Archived = 2
    Draft = 3
    Disabled = 4
    Removed = 5


@unique
class PropertyTypes(StrChoicesEnum):
    @property
    def pretty_name(self):
        if self == self.Camper_Rv:
            name = "Camper/RV"
        elif self == self.Caravan_Mobile_Home:
            name = "Caravan/Mobile Home"
        elif self == self.Ski_Inn:
            name = "Ski-in/Ski-out"
        else:
            name = self.name.replace("_", " ")
        return name

    Aparthotel = "AH"
    Apartment = "AP"
    Barn = "BA"
    Bed_and_Breakfast = "BB"
    Beach_Hut = "BH"
    Boat = "BO"
    Boutique_Hotel = "BP"
    Bungalow = "BU"
    Cabin = "CA"
    Camper_Rv = "CR"
    Campsite = "CP"
    Caravan_Mobile_Home = "CM"
    Casa_Particular = "CN"
    Castle = "CS"
    Cave = "CV"
    Chalet = "CH"
    Chateau = "CU"
    Condo = "CO"
    Converted_Chapel = "CC"
    Cottage = "CT"
    Cycladic_House = "CY"
    Dammuso = "DA"
    Dome_House = "DH"
    Dorm = "DR"
    Earth_House = "EH"
    Estate = "ES"
    Farmhouse = "FA"
    Finca = "FI"
    Fort = "FO"
    Gite = "GI"
    Guest_Suite = "GS"
    Guesthouse = "GH"
    Heritage_Hotel = "HH"
    Hostel = "HS"
    Hotel = "HT"
    House = "HO"
    Houseboat = "HB"
    Hut = "HU"
    Igloo = "IG"
    In_Law = "IL"
    Inn = "IN"
    Island = "IS"
    Light_House = "LH"
    Lodge = "LD"
    Loft = "LO"
    Manor_House = "MH"
    Minsu = "MI"
    Mobile_Home = "MB"
    Narrow_Boat = "NB"
    Other = "OT"
    Pension = "PE"
    Pent_House = "PH"
    Plane = "PL"
    Resort = "RE"
    Room = "RO"
    Riad = "RI"
    Ryokan = "RY"
    Serviced_Apartment = "SA"
    Ski_Inn = "SI"
    Studio = "ST"
    Shepherds_Hut = "SH"
    Ski_Chalet = "SC"
    Tented_Camp = "TC"
    Tent = "TE"
    Tiny_House = "TF"
    Tipi = "TI"
    Tower = "TW"
    Townhouse = "TH"
    Train = "TR"
    Treehouse = "TO"
    Trullo = "TU"
    Vacation_Home = "VH"
    Villa = "VI"
    Watermill = "WA"
    Windmill = "WI"
    Yacht = "YA"
    Yurt = "YU"


class SyncStatus(IntChoicesEnum):
    Succes = 1
    Pending = 2
    Error = 3


class WeekDays(IntChoicesEnum):
    Monday = 0
    Tuesday = 1
    Wednesday = 2
    Thursday = 3
    Friday = 4
    Saturday = 5
    Sunday = 6


class ParkingType(StrChoicesEnum):
    """
    Main Parking
    """

    # Housing for car, may or may not be attached to house
    garage = "GRG"
    # Exposed parking lot
    surface_lot = "SRF"
    # Covered parking lot (i.e. carport)
    covered = "CVD"
    # Other parking, use parking_description
    other = "OTH"
    # No unit parking available
    none = "NON"


class LaundryType(StrChoicesEnum):
    shared = "SHD"
    in_unit = "INU"
    coin_op = "COP"
    none = "NON"


class CancellationReasons(IntChoicesEnum):
    other = 0
    renter = 1
    dates = 2
    payment = 3
    fraud = 4

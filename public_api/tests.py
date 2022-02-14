import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from unittest import mock

import pytz
from django.test import TestCase
from django.utils import timezone
from guardian.shortcuts import assign_perm
from psycopg2._range import DateRange
from rest_framework.test import APIClient

from accounts.models import Organization, Token
from crm.models import Contact
from listings import choices, models
from . import views
from .serializers import PropertySerializer

minimal_png = b"""\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00
\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01
\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"""
MIN_NIGHTS = 5
MAX_NIGHTS = 30
NIGHTLY_PRICE = 100.00
NIGHTLY_PRICE_STR = "$100.00"
CHECK_IN_START = "8:10"
CHECK_IN_TO = "12:20"
CHECK_OUT_UNTIL = "10:30"
GUEST_IMAGE_URL = "https://cdn.voyajoy.com/images/about/team/ivan.jpg"
IMAGE_URLS = [
    "relative/path/1.png",
    "does/not/exist/404.png",
    "http://example.org/path/2"
]


class ReservationViewSetTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create()
        cls.prop = models.Property.objects.create(
            name="Name",
            property_type=models.Property.Types.Apartment.value,
            rental_type=models.Property.Rentals.Private.value,
            organization=cls.organization,
        )

        start = timezone.now().date()
        end = start + timedelta(days=10)

        cls.guest = Contact.objects.create(organization=cls.organization)
        cls.res = models.Reservation.objects.create(
            start_date=start,
            end_date=end,
            price=Decimal("0"),
            paid=Decimal("0.00"),
            prop_id=cls.prop.id,
            confirmation_code="abcd",
            guest=cls.guest,
            status=models.Reservation.Statuses.Accepted.value,
        )

    # def test_cancel(self):
    #     kwargs = {"user.organization": self.organization}
    #
    #     request = mock.MagicMock(**kwargs)
    #
    #     view = views.ReservationViewSet()
    #     view.kwargs = {"confirmation_code": self.res.confirmation_code}
    #     view.request = request
    #     view.action = "PATCH"
    #     view.format_kwarg = None
    #
    #     resp_data = view.cancel(request, self.res.confirmation_code).data
    #
    #     self.assertEqual(resp_data["status"], models.Reservation.Statuses.Cancelled.name)

    def test_get_serializer_context(self):
        view = views.ReservationViewSet(request=mock.Mock(), format_kwarg=None)
        self.assertIn("organization", view.get_serializer_context())


class ApiEndPointsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        organization = Organization.objects.create()
        token = Token.objects.create(name="Test token", organization=organization)

        cls.format = "%Y-%m-%dT%H:%M:%S.%fZ"
        cls.maxDiff = None

        cls.api_client = APIClient()
        cls.api_client.credentials(HTTP_AUTHORIZATION="Token: {}".format(token.key))

        cls.group = group = models.Group.objects.create(
            name="My Group",
            description="Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
            organization=organization,
        )

        cls.prop = models.Property.objects.create(
            name="Property Name",
            max_guests=5,
            property_type=models.Property.Types.Apartment.value,
            rental_type=models.Property.Rentals.Private.value,
            organization=organization,
            external_id=str(uuid.uuid4()),
            location=models.Location.objects.create(
                continent="Europe",
                country="Poland",
                country_code="PL",
                state="Lower Silesia",
                city="Wrocław",
                address="Lorem ipsum",
                apartment="dolor sit amet",
                postal_code="50-041",
                latitude=1.0,
                longitude=1.0,
            ),
            bathrooms=1.0,
            bedrooms=2.0,
            status=models.Property.Statuses.Active.value,
            group=group,
        )
        assign_perm("public_api_access", token.user, cls.prop)

        cls.basic_amenities = models.BasicAmenities.objects.create(
            essentials=True,
            ac=True,
            hair_dryer=True,
            dishes_and_silverware=True,
            wide_clearance_to_bed=True,
            bedroom_wide_doorway=True,
            accessible_height_bed=True,
            prop=cls.prop,
        )
        models.ListingDescriptions.objects.create(
            headline="Cool Property",
            description="Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
            house_manual="Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
            prop=cls.prop,
        )
        models.PricingSettings.objects.create(
            nightly=100,
            currency=choices.Currencies.USD.value,
            cleaning_fee=100,
            security_deposit=500,
            extra_person_fee=10,
            included_guests=2,
            prop=cls.prop,
        )
        cls.booking_settings = models.BookingSettings.objects.create(
            months_advanced_bookable=12, prop=cls.prop
        )
        models.CheckInOut.objects.create(
            check_in_from=CHECK_IN_START,
            check_in_to=CHECK_IN_TO,
            check_out_until=CHECK_OUT_UNTIL,
            booking_settings=cls.booking_settings,
        )
        models.AvailabilitySettings.objects.create(
            min_stay=MIN_NIGHTS,
            max_stay=MAX_NIGHTS,
            advance_notice=2,
            preparation=1,
            prop=cls.prop,
        )
        cls.custom_amenity = models.Feature.objects.create(name="Custom Amenity", value=1)
        cls.prop.features.add(cls.custom_amenity)

        cls.stay_requirements = models.Availability.objects.create(
            min_stay=MIN_NIGHTS,
            max_stay=MAX_NIGHTS,
            min_age=10,
            preparation=2,
            advance_notice=3,
            booking_window_months=4,
            time_frame=DateRange(date(2018, 1, 1), date(2018, 12, 31)),
            prop=cls.prop,
        )

        cls.rate = models.Rate.objects.create(
            nightly=Decimal("100"), time_frame=DateRange(None, None), prop=cls.prop
        )

        cls.guest = Contact.objects.create(
            organization=organization
        )
        cls.res = models.Reservation.objects.create(
            start_date=date(2019, 4, 1),
            end_date=date(2019, 4, 5),
            price=10000,
            base_total=1600,
            paid=0,
            guest=cls.guest,
            prop=cls.prop,
            confirmation_code="ABC123"
        )

        cls.image = models.Image.objects.create(
            url=IMAGE_URLS[0], prop_id=cls.prop.pk, order=1, caption="abcd"
        )
        cls.image.url.save("1.png", BytesIO(minimal_png))
        cls.image_invalid = models.Image.objects.create(
            url=IMAGE_URLS[1], prop_id=cls.prop.pk, order=3, caption="vxyz"
        )
        models.Image.objects.create(
            url=IMAGE_URLS[2], prop_id=cls.prop.pk, order=2, caption="efgh"
        )

        cls.fee = models.AdditionalFee.objects.create(
            name="Some Custom Fee",
            value=10,
            optional=False,
            calculation_method=choices.CalculationMethod.Per_Person_Per_Stay.value,
            fee_tax_type=models.AdditionalFee.FeeTypes.Towel_Fee.value,
            prop=cls.prop,
        )
        models.Discount.objects.create(
            value=2,
            prop=cls.prop,
            is_percentage=False,
            days_before=10,
            discount_type=models.Discount.Types.Late_Bird.value,
            calculation_method=choices.CalculationMethod.Per_Stay.value,
        )

        models.Suitability.objects.create(
            prop=cls.prop,
            elderly=models.Suitability.SuitabilityProvided.Yes.value,
            pets=models.Suitability.SuitabilityProvided.No.value,
            kids=models.Suitability.SuitabilityProvided.Unknown.value,
            events=models.Suitability.SuitabilityProvided.Unknown.value,
            large_groups=models.Suitability.SuitabilityProvided.Inquire.value,
            smoking=models.Suitability.SuitabilityProvided.No.value,
            handicap=models.Suitability.SuitabilityProvided.Yes.value,
            infants=models.Suitability.SuitabilityProvided.Yes.value,
        )

    def test_rental_list(self):
        resp = self.api_client.get("/api/v1/properties/")

        self.assertEqual(resp.status_code, 200)

        resp_json = resp.json()
        self.assertEqual(
            resp_json,
            [
                {
                    "id": self.prop.id,
                    "dateUpdated": self.prop.date_updated.strftime(self.format),
                    "status": choices.PropertyStatuses(self.prop.status).pretty_name,
                }
            ],
        )

        with self.subTest("GET: Rentals, Group Filter"):
            with self.subTest("Group with results"):
                resp = self.api_client.get(
                    "/api/v1/properties/?group={group}".format(group=self.group.id)
                )

                self.assertEqual(resp.status_code, 200)

                resp_json = resp.json()
                self.assertEqual(len(resp_json), 1)

            with self.subTest("Group with no results"):
                resp = self.api_client.get("/api/v1/properties/?group={group}".format(group=123))

                self.assertEqual(resp.status_code, 200)

                resp_json = resp.json()
                self.assertEqual(len(resp_json), 0)

    def test_properties_detail(self):

        with mock.patch("cozmo.storages.DOStorage.url", side_effect=lambda x: "IMAGE_URL"):
            resp = self.api_client.get("/api/v1/properties/{id}/".format(id=self.prop.id))

            self.assertEqual(resp.status_code, 200)
            serializer = PropertySerializer(instance=self.prop)
            resp_json = resp.json()
            self.assertDictEqual(
                resp_json,
                {
                    "id": self.prop.id,
                    "name": self.prop.name,
                    "headline": self.prop.descriptions.headline,
                    "continent": self.prop.location.continent,
                    "country": self.prop.location.country,
                    "region": self.prop.location.region,
                    "state": self.prop.location.state,
                    "city": self.prop.location.city,
                    "postalCode": self.prop.location.postal_code,
                    "address1": self.prop.location.address,
                    "address2": self.prop.location.apartment,
                    "amenities": {
                        'ac': True,
                        'accessibleHeightBed': True,
                        'accessibleHeightToilet': False,
                        'airportShuttle': False,
                        'babyBath': False,
                        'babyMonitor': False,
                        'babysitterRecommendations': False,
                        'bathroomStepFreeAccess': False,
                        'bathroomWideDoorway': False,
                        'bathtub': False,
                        'bbqArea': False,
                        'beachEssentials': False,
                        'beachfront': False,
                        'bedLinens': False,
                        'bedroomStepFreeAccess': False,
                        'bedroomWideDoorway': True,
                        'breakfast': False,
                        'cable': False,
                        'carRental': False,
                        'carbonMonoxideDetector': False,
                        # 'catsAllowed': False,
                        'ceilingHoist': False,
                        'changingTable': False,
                        'childrensBooksAndToys': False,
                        'childrensDinnerware': False,
                        'cleaningBeforeCheckout': False,
                        'coffeeMaker': False,
                        'commonSpaceStepFreeAccess': False,
                        'commonSpaceWideDoorway': False,
                        'cookingBasics': False,
                        'cooling': False,
                        'crib': False,
                        'disabledParkingSpot': False,
                        'dishesAndSilverware': True,
                        'dishwasher': False,
                        # 'dogsAllowed': False,
                        'dryer': False,
                        'electricProfilingBed': False,
                        'elevator': False,
                        'essentials': True,
                        'ethernetConnection': False,
                        'evCharger': False,
                        'extraPillowsAndBlankets': False,
                        'fireExtinguisher': False,
                        'fireplace': False,
                        'fireplaceGuards': False,
                        'firstAidKit': False,
                        'flatSmoothPathwayToFrontDoor': False,
                        'freeBreakfast': False,
                        'freeParking': False,
                        'furnished': False,
                        'gameConsole': False,
                        'gardenOrBackyard': False,
                        'gated': False,
                        'grabRailsInShower': False,
                        'grabRailsInToilet': False,
                        'gym': False,
                        'hairDryer': True,
                        'handheldShowerHead': False,
                        'hangers': False,
                        'hardwoodFlooring': False,
                        'heating': False,
                        'highChair': False,
                        'homeStepFreeAccess': False,
                        'homeWideDoorway': False,
                        'hotTub': False,
                        'hotWater': False,
                        'internet': False,
                        'iron': False,
                        'jacuzzi': False,
                        'kitchen': False,
                        'lakeAccess': False,
                        'laptopFriendly': False,
                        # 'largeDogsAllowed': False,
                        'laundry': False,
                        # 'laundryType': 'NON',
                        'lockOnBedroomDoor': False,
                        'longTermStaysAllowed': False,
                        'luggageDropoffAllowed': False,
                        'microwave': False,
                        'mobileHoist': False,
                        'outletCovers': False,
                        'oven': False,
                        'packNPlayTravelCrib': False,
                        'paidParking': False,
                        'paidParkingOnPremises': False,
                        'parking': False,
                        # 'parkingDescription': '',
                        # 'parkingFee': None,
                        # 'parkingType': 'NON',
                        'pathToEntranceLitAtNight': False,
                        'patioOrBalcony': False,
                        'pocketWifi': False,
                        'pool': False,
                        'poolHoist': False,
                        'privateEntrance': False,
                        'privateLivingRoom': False,
                        'refrigerator': False,
                        'rollinShower': False,
                        'roomDarkeningShades': False,
                        'roomService': False,
                        'shampoo': False,
                        'showerChair': False,
                        'singleLevelHome': False,
                        'skiInSkiOut': False,
                        'smokeDetector': False,
                        'stairGates': False,
                        'stove': False,
                        'streetParking': False,
                        'tableCornerGuards': False,
                        'tubWithShowerBench': False,
                        'tv': False,
                        'washer': False,
                        'waterfront': False,
                        'wheelchair': False,
                        'wideClearanceToBed': True,
                        'wideClearanceToShowerAndToilet': False,
                        'wideHallwayClearance': False,
                        'windowGuards': False,
                        'wirelessInternet': False,
                    },
                    "customAmenities": [self.custom_amenity.name],
                    "icalUrl": self.prop.cozmo_calendar.url,
                    "images": [
                        {
                            "caption": self.image.caption,
                            "downloadUrls": {
                                "raw": {
                                    "url": self.image.url.url,
                                    "width": self.image.url.width,
                                    "height": self.image.url.height,
                                }
                            },
                            "id": self.image.id,
                            "sortOrder": self.image.order,
                        },
                        {
                            "caption": self.image_invalid.caption,
                            "downloadUrls": {
                                "raw": {
                                    "url": self.image_invalid.url.url,
                                    "width": None,
                                    "height": None,
                                }
                            },
                            "id": self.image_invalid.id,
                            "sortOrder": self.image_invalid.order,
                        },
                    ],
                    "legacyId": "",
                    "isAvailable": serializer.get_is_available(self.prop),
                    "latitude": format(self.prop.location.latitude, ".12f"),
                    "longitude": format(self.prop.location.longitude, ".12f"),
                    "bathrooms": format(self.prop.bathrooms, ".1f"),
                    "bedrooms": format(self.prop.bedrooms, ".1f"),
                    "accommodates": self.prop.max_guests,
                    "description": self.prop.descriptions.description,
                    "currency": choices.Currencies.USD.pretty_name,
                    "checkInTime": CHECK_IN_START,
                    "checkOutTime": CHECK_OUT_UNTIL,
                    "maxGuests": self.prop.max_guests,
                    "monthsAdvancedBookable": self.prop.booking_settings.months_advanced_bookable,
                    "suitability": {
                        "elderly": models.Suitability.SuitabilityProvided.Yes.name,
                        "events": models.Suitability.SuitabilityProvided.Unknown.name,
                        "pets": models.Suitability.SuitabilityProvided.No.name,
                        "kids": models.Suitability.SuitabilityProvided.Unknown.name,
                        "largeGroups": models.Suitability.SuitabilityProvided.Inquire.name,
                        "smoking": models.Suitability.SuitabilityProvided.No.name,
                        "handicap": models.Suitability.SuitabilityProvided.Yes.name,
                        "infants": models.Suitability.SuitabilityProvided.Yes.name,
                        "childrenNotAllowedDetails": ""
                    },
                    "propertyType": self.prop.Types.Apartment.name,
                    "roomType": self.prop.Rentals.Private.name,
                    "rooms": list(),
                    "status": self.prop.Statuses.Active.name,
                    "fullAddress": (
                        "Lorem ipsum, dolor sit amet, Wrocław, Lower Silesia 50-041, PL"
                    ),
                    "dateUpdated": self.prop.date_updated.strftime(self.format),
                    "defaultMinNights": self.prop.availability_settings.min_stay,
                    "defaultMaxNights": self.prop.availability_settings.max_stay,
                    "bookingLeadTime": self.prop.availability_settings.advance_notice,
                    "preparationTime": self.prop.availability_settings.preparation,
                    "defaultNightlyPrice": format(NIGHTLY_PRICE, ".2f"),
                    "cleaningFee": "100.00",
                    "securityDeposit": "500.00",
                    "extraPersonFee": "10.00",
                    "includedGuests": self.prop.pricing_settings.included_guests,
                },
            )

    def test_stay_requirements(self):
        resp = self.api_client.get(
            "/api/v1/properties/{prop_id}/stayrequirements/".format(prop_id=self.prop.id)
        )

        self.assertEqual(resp.status_code, 200)

        resp_json = resp.json()
        self.assertEqual(
            resp_json,
            {
                "dateUpdated": self.stay_requirements.date_updated.strftime(self.format),
                "data": [
                    {
                        "id": self.stay_requirements.id,
                        "startDate": str(self.stay_requirements.time_frame.lower),
                        "endDate": str(self.stay_requirements.time_frame.upper),
                        "minStay": self.stay_requirements.min_stay,
                        "maxStay": self.stay_requirements.max_stay,
                        "minAge": self.stay_requirements.min_age,
                        "preparation": self.stay_requirements.preparation,
                        "advanceNotice": self.stay_requirements.advance_notice,
                        "window": self.stay_requirements.booking_window_months,
                    }
                ],
            },
        )

    def test_availability(self):
        with self.subTest("Default Values"):
            with mock.patch("cozmo_common.filters.timezone.now") as mock_tz:
                today_dt = datetime(
                    year=2018, month=1, day=12, tzinfo=pytz.timezone("America/New_York")
                )
                mock_tz.return_value = today_dt

                today = today_dt.date()
                resp = self.api_client.get(
                    "/api/v1/properties/{prop_id}/availability/".format(prop_id=self.prop.id)
                )

                self.assertEqual(resp.status_code, 200)

                resp_json = resp.json()
                self.assertEqual(
                    resp_json,
                    {
                        "adults": 0,
                        "children": 0,
                        "pets": 0,
                        "available": True,
                        "arrivalDate": str(today),
                        "departureDate": str(today + timedelta(days=30)),
                        "nights": 30,
                    },
                )

    def test_quote(self):
        currency_symbol = choices.Currencies[self.prop.pricing_settings.currency].symbol

        with self.subTest("Default Values"):
            with mock.patch("cozmo_common.filters.timezone.now") as mock_tz:
                today_dt = datetime(
                    year=2018, month=1, day=12, tzinfo=pytz.timezone("America/New_York")
                )
                mock_tz.return_value = today_dt

                today = today_dt.date()
                resp = self.api_client.get(
                    "/api/v1/properties/{prop_id}/quotes/".format(prop_id=self.prop.id)
                )

                self.assertEqual(resp.status_code, 200)

                resp_json = resp.json()
                self.assertEqual(
                    resp_json,
                    {
                        "adults": 0,
                        "children": 0,
                        "pets": 0,
                        "available": True,
                        "arrivalDate": str(today),
                        "departureDate": str(today + timedelta(days=30)),
                        "nights": 30,
                        "currency": choices.Currencies.USD.value,
                        "totalPrice": 2998.0,
                        "totalPriceFormatted": "{0}2998.00".format(currency_symbol),
                        "fees": [
                            {
                                "feeTaxType": models.AdditionalFee.FeeTypes.Towel_Fee.pretty_name,
                                "name": "Some Custom Fee",
                                "amount": "0.00",
                                "amountFormatted": "{0}0.00".format(currency_symbol),
                                "refundable": False,
                                "optional": False,
                                "taxable": False,
                            }
                        ],
                        "rate": {
                            "duration": 30,
                            "amount": "3000.00",
                            "amountFormatted": "{0}3000.00".format(currency_symbol),
                        },
                        "discounts": [
                            {
                                "discountType": models.Discount.Types.Late_Bird.pretty_name,
                                "amount": "2.00",
                                "amountFormatted": "{0}2.00".format(currency_symbol),
                                "optional": False,
                            }
                        ],
                        "baseTotal": "3000.00",
                        "nightlyPrice": "100.00"
                    },
                )

        with self.subTest("Custom Date"):
            arrival_date = date(2018, 10, 10)
            departure_date = date(2018, 11, 1)
            resp = self.api_client.get(
                "/api/v1/properties/{prop_id}/quotes/?from={f}&to={t}".format(
                    prop_id=self.prop.id, f=str(arrival_date), t=str(departure_date)
                )
            )

            self.assertEqual(resp.status_code, 200)

            resp_json = resp.json()
            self.assertEqual(
                resp_json,
                {
                    "adults": 0,
                    "children": 0,
                    "pets": 0,
                    "available": True,
                    "arrivalDate": str(arrival_date),
                    "departureDate": str(departure_date),
                    "nights": 22,
                    "currency": choices.Currencies.USD.value,
                    "totalPrice": 2198.0,
                    "totalPriceFormatted": "{0}2198.00".format(currency_symbol),
                    "fees": [
                        {
                            "feeTaxType": models.AdditionalFee.FeeTypes.Towel_Fee.pretty_name,
                            "name": "Some Custom Fee",
                            "amount": "0.00",
                            "amountFormatted": "{0}0.00".format(currency_symbol),
                            "refundable": False,
                            "optional": False,
                            "taxable": False,
                        }
                    ],
                    "rate": {
                        "duration": 22,
                        "amount": "2200.00",
                        "amountFormatted": "{0}2200.00".format(currency_symbol),
                    },
                    "discounts": [
                        {
                            "discountType": models.Discount.Types.Late_Bird.pretty_name,
                            "amount": "2.00",
                            "amountFormatted": "{0}2.00".format(currency_symbol),
                            "optional": False,
                        }
                    ],
                    "baseTotal": "2200.00",
                    "nightlyPrice": "100.00"
                },
            )

        with self.subTest("All Custom"):
            arrival_date = date(2018, 10, 10)
            departure_date = date(2018, 11, 1)
            resp = self.api_client.get(
                "/api/v1/properties/"
                + "{prop_id}/quotes/?from={f}&to={t}&adults={a}&children={c}&pets={p}".format(
                    prop_id=self.prop.id, f=str(arrival_date), t=str(departure_date), a=2, c=3, p=1
                )
            )

            self.assertEqual(resp.status_code, 200)

            resp_json = resp.json()
            self.assertEqual(
                resp_json,
                {
                    "adults": 2,
                    "children": 3,
                    "pets": 1,
                    "available": True,
                    "arrivalDate": str(arrival_date),
                    "departureDate": str(departure_date),
                    "nights": 22,
                    "currency": choices.Currencies.USD.value,
                    "totalPrice": 2198.0,
                    "totalPriceFormatted": "{0}2198.00".format(currency_symbol),
                    "fees": [
                        {
                            "feeTaxType": models.AdditionalFee.FeeTypes.Towel_Fee.pretty_name,
                            "name": "Some Custom Fee",
                            "amount": "0.00",
                            "amountFormatted": "{0}0.00".format(currency_symbol),
                            "refundable": False,
                            "optional": False,
                            "taxable": False,
                        }
                    ],
                    "rate": {
                        "duration": 22,
                        "amount": "2200.00",
                        "amountFormatted": "{0}2200.00".format(currency_symbol),
                    },
                    "discounts": [
                        {
                            "discountType": models.Discount.Types.Late_Bird.pretty_name,
                            "amount": "2.00",
                            "amountFormatted": "{0}2.00".format(currency_symbol),
                            "optional": False,
                        }
                    ],
                    "baseTotal": "2200.00",
                    "nightlyPrice": "100.00",

                },
            )

        with self.subTest("Months advanced bookable"):
            arrival_date = date.today() + timedelta(
                days=self.prop.booking_settings.months_advanced_bookable * 30 + 1
            )
            departure_date = arrival_date + timedelta(days=5)
            resp = self.api_client.get(
                "/api/v1/properties/{prop_id}/quotes/?from={f}&to={t}".format(
                    prop_id=self.prop.id, f=str(arrival_date), t=str(departure_date)
                )
            )

            self.assertEqual(resp.status_code, 200)

            resp_json = resp.json()
            self.assertEqual(
                resp_json,
                {
                    "adults": 0,
                    "children": 0,
                    "pets": 0,
                    "available": False,
                    "arrivalDate": str(arrival_date),
                    "departureDate": str(departure_date),
                    "nights": (departure_date - arrival_date).days,
                },
            )

        with self.subTest("All Custom, Blocked Date"):
            # Blocker
            models.Blocking.objects.create(time_frame=(None, None), prop=self.prop)

            arrival_date = date(2018, 10, 10)
            departure_date = date(2018, 11, 1)
            resp = self.api_client.get(
                "/api/v1/properties/"
                + "{prop_id}/quotes/?from={f}&to={t}&adults={a}&children={c}&pets={p}".format(
                    prop_id=self.prop.id, f=str(arrival_date), t=str(departure_date), a=2, c=3, p=1
                )
            )

            self.assertEqual(resp.status_code, 200)
            resp_json = resp.json()
            self.assertEqual(
                resp_json,
                {
                    "adults": 2,
                    "children": 3,
                    "pets": 1,
                    "available": False,
                    "arrivalDate": str(arrival_date),
                    "departureDate": str(departure_date),
                    "nights": 22,
                },
            )

    def test_reservation_create(self):
        data = {
            "startDate": "2018-08-01",
            "endDate": "2018-08-10",
            "status": "Accepted",  # Optional
            "guestsAdults": 2,
            "guestsChildren": 1,
            "pets": 1,
            "paid": 0,
            "privateNotes": "Private Note",
            "rebookAllowedIfCancelled": True,
            "externalId": str(uuid.uuid4()),
            "connectionId": str(uuid.uuid4()),  # Optional Currently not used
            "prop": self.prop.id,
            "guest": {
                "firstName": "John",
                "lastName": "Smith",
                "email": "john.smith@voyajoy.com",
                "secondaryEmail": "john.smith+1@voyajoy.com",
                "phone": "123456789",
                "secondaryPhone": "223456789",
                "avatar": "https://cdn.voyajoy.com/images/about/team/ivan.jpg",
                "location": "Contact Location",
                "note": "Some Note",
            },  # optional
        }

        with mock.patch("cozmo.storages.DOStorage.url", return_value=GUEST_IMAGE_URL):
            resp = self.api_client.post("/api/v1/reservations/", data)

            self.assertEqual(resp.status_code, 201, resp.json())

            resp_json = resp.json()
            reservation = models.Reservation.objects.get(
                confirmation_code=resp_json.get("confirmationCode")
            )
            currency_symbol = choices.Currencies[reservation.prop.pricing_settings.currency].symbol
            self.assertEqual(
                resp_json,
                {
                    "guest": {
                        "id": reservation.guest.id,
                        "avatar": GUEST_IMAGE_URL,
                        "firstName": reservation.guest.first_name,
                        "lastName": reservation.guest.last_name,
                        "email": reservation.guest.email,
                        "secondaryEmail": reservation.guest.secondary_email,
                        "phone": reservation.guest.phone,
                        "secondaryPhone": reservation.guest.secondary_phone,
                        "location": reservation.guest.location,
                        "note": reservation.guest.note,
                    },
                    "discounts": [
                        {
                            "discountType": models.Discount.Types.Late_Bird.pretty_name,
                            "amount": str(reservation.reservationdiscount_set.first().value),
                            "amountFormatted": "{0}{1}".format(
                                currency_symbol,
                                str(reservation.reservationdiscount_set.first().value),
                            ),
                            "optional": reservation.reservationdiscount_set.first().optional,
                        }
                    ],
                    "fees": [
                        {
                            "feeTaxType": models.AdditionalFee.FeeTypes.Towel_Fee.pretty_name,
                            "name": reservation.reservationfee_set.last().name,
                            "amount": str(reservation.reservationfee_set.last().value),
                            "amountFormatted": "{0}{1}".format(
                                currency_symbol, str(reservation.reservationfee_set.last().value)
                            ),
                            "refundable": reservation.reservationfee_set.last().refundable,
                            "optional": reservation.reservationfee_set.last().optional,
                            "taxable": reservation.reservationfee_set.last().taxable,
                        }
                    ],
                    "rate": {
                        "duration": reservation.nights,
                        "amount": str(reservation.nightly_price),
                        "amountFormatted": "{0}{1}".format(
                            currency_symbol, str(reservation.nightly_price)
                        )
                    },
                    "startDate": str(reservation.start_date),
                    "endDate": str(reservation.end_date),
                    "status": reservation.Statuses.Accepted.pretty_name,
                    "price": str(reservation.price),
                    "priceFormatted": "{0}{1}".format(currency_symbol, str(reservation.price)),
                    "paid": str(reservation.paid),
                    "guestsAdults": reservation.guests_adults,
                    "guestsChildren": reservation.guests_children,
                    "guestsInfants": reservation.guests_infants,
                    "pets": reservation.pets,
                    "externalId": reservation.external_id,
                    "confirmationCode": reservation.confirmation_code,
                    "prop": reservation.prop.id,
                    "dateUpdated": reservation.date_updated.strftime(self.format),
                    "dateCreated": reservation.date_created.strftime(self.format),
                    "currency": reservation.prop.pricing_settings.currency,
                    "baseTotal": str(reservation.base_total),
                    "nightlyPrice": str(reservation.nightly_price),
                    "nights": reservation.nights
                },
            )

    def test_reservation_detail(self):
        resp = self.api_client.get(
            "/api/v1/reservations/{confirmation_code}/".format(
                confirmation_code=self.res.confirmation_code
            )
        )

        self.assertEqual(resp.status_code, 200)
        self.res.refresh_from_db()
        currency_symbol = choices.Currencies[self.res.prop.pricing_settings.currency].symbol

        resp_json = resp.json()
        self.assertDictEqual(
            resp_json,
            {
                "guest": {
                    "avatar": "",
                    "email": self.guest.email,
                    "firstName": self.guest.first_name,
                    "id": self.guest.id,
                    "lastName": self.guest.last_name,
                    "location": self.guest.location,
                    "note": self.guest.note,
                    "phone": self.guest.phone,
                    "secondaryEmail": self.guest.secondary_email,
                    "secondaryPhone": self.guest.secondary_phone,
                },
                "discounts": [],
                "fees": [],
                "rate": {"amount": "400.00", "amountFormatted": "$400.00", "duration": 4},
                "startDate": str(self.res.start_date),
                "endDate": str(self.res.end_date),
                "status": self.res.Statuses.Accepted.pretty_name,
                "price": str(self.res.price),
                "priceFormatted": "{0}{1}".format(currency_symbol, str(self.res.price)),
                "paid": str(self.res.paid),
                "guestsAdults": self.res.guests_adults,
                "guestsChildren": self.res.guests_children,
                "guestsInfants": self.res.guests_infants,
                "pets": self.res.pets,
                "prop": self.res.prop.id,
                "externalId": self.res.external_id,
                "confirmationCode": self.res.confirmation_code,
                "dateUpdated": self.res.date_updated.strftime(self.format),
                "dateCreated": self.res.date_created.strftime(self.format),
                "baseTotal": str(self.res.base_total),
                "currency": self.res.prop.pricing_settings.currency,
                "nightlyPrice": str(self.res.nightly_price),
                "nights": self.res.nights
            },
        )

    def test_reservation_cancel(self):
        resp = self.api_client.patch(
            "/api/v1/reservations/{confirmation_code}/cancellation/".format(
                confirmation_code=self.res.confirmation_code
            )
        )

        self.assertEqual(resp.status_code, 200)
        self.res.refresh_from_db()
        currency_symbol = choices.Currencies[self.res.prop.pricing_settings.currency].symbol

        resp_json = resp.json()
        self.assertDictEqual(
            resp_json,
            {
                "guest": {
                    "avatar": "",
                    "email": self.guest.email,
                    "firstName": self.guest.first_name,
                    "id": self.guest.id,
                    "lastName": self.guest.last_name,
                    "location": self.guest.location,
                    "note": self.guest.note,
                    "phone": self.guest.phone,
                    "secondaryEmail": self.guest.secondary_email,
                    "secondaryPhone": self.guest.secondary_phone,
                },
                "discounts": [],
                "fees": [],
                "rate": {"amount": "400.00", "amountFormatted": "$400.00", "duration": 4},
                "startDate": str(self.res.start_date),
                "endDate": str(self.res.end_date),
                "status": self.res.Statuses.Cancelled.pretty_name,
                "price": str(self.res.price),
                "priceFormatted": "{0}{1}".format(currency_symbol, str(self.res.price)),
                "paid": str(self.res.paid),
                "guestsAdults": self.res.guests_adults,
                "guestsChildren": self.res.guests_children,
                "guestsInfants": self.res.guests_infants,
                "pets": self.res.pets,
                "externalId": self.res.external_id,
                "confirmationCode": self.res.confirmation_code,
                "prop": self.res.prop.id,
                "dateUpdated": self.res.date_updated.strftime(self.format),
                "dateCreated": self.res.date_created.strftime(self.format),
                "baseTotal": str(self.res.base_total),
                "nightlyPrice": str(self.res.nightly_price),
                "currency": self.res.prop.pricing_settings.currency,
                "nights": self.res.nights
            },
        )

    def test_rate(self):
        seasonal_rate = models.Rate.objects.create(
            nightly=200,
            weekend=250,
            weekly=100,
            monthly=100,
            extra_person_fee=200,
            time_frame=DateRange(date(2019, 2, 1), date(2019, 3, 10)),
            prop=self.prop,
        )

        resp = self.api_client.get(
            "/api/v1/properties/{prop_id}/rates/".format(prop_id=self.prop.id)
        )

        self.assertEqual(resp.status_code, 200)

        resp_json = resp.json()

        self.assertEqual(len(resp_json), 2)
        self.assertEqual(
            resp_json["dateUpdated"], seasonal_rate.date_updated.strftime(self.format)
        )
        self.assertDictEqual(
            resp_json["data"][0],
            {
                "id": self.rate.id,
                "startDate": self.rate.time_frame.lower,
                "endDate": self.rate.time_frame.upper,
                "nightly": format(self.rate.nightly, ".2f"),
                "weekend": None,
                "weekly": format(self.rate.weekly, ".2f"),
                "monthly": format(self.rate.monthly, ".2f"),
                "extraPerson": None,
            },
        )
        self.assertEqual(
            resp_json["data"][1],
            {
                "id": seasonal_rate.id,
                "startDate": str(seasonal_rate.time_frame.lower),
                "endDate": str(seasonal_rate.time_frame.upper),
                "nightly": format(seasonal_rate.nightly, ".2f"),
                "weekend": format(seasonal_rate.weekend, ".2f"),
                "weekly": format(seasonal_rate.weekly, ".2f"),
                "monthly": format(seasonal_rate.monthly, ".2f"),
                "extraPerson": format(seasonal_rate.extra_person_fee, ".2f"),
            },
        )

    def test_blockings(self):

        with self.subTest("No Blockings"):
            resp = self.api_client.get(
                "/api/v1/properties/{prop_id}/blockings/?from={f}&to={t}".format(
                    prop_id=self.prop.id, f="2019-01-01", t="2019-01-10"
                )
            )

            self.assertEqual(resp.status_code, 200)
            resp_json = resp.json()
            self.assertEqual(resp_json, {"dateUpdated": 0, "data": []})

        with self.subTest("There are Blockings"):
            blocking = models.Blocking.objects.create(time_frame=(None, None), prop=self.prop)
            resp = self.api_client.get(
                "/api/v1/properties/{prop_id}/blockings/?from={f}&to={t}".format(
                    prop_id=self.prop.id, f="2019-01-01", t="2019-01-10"
                )
            )

            self.assertEqual(resp.status_code, 200)
            resp_json = resp.json()
            self.assertEqual(
                resp_json,
                {
                    "dateUpdated": blocking.date_updated.strftime(self.format),
                    "data": [{"endDate": "2019-01-10", "startDate": "2019-01-01"}],
                },
            )

    def test_fees(self):
        resp = self.api_client.get(
            "/api/v1/properties/{prop_id}/fees/".format(prop_id=self.prop.id)
        )

        self.assertEqual(resp.status_code, 200)

        resp_json = resp.json()
        self.assertEqual(
            resp_json,
            {
                "dateUpdated": self.fee.date_updated.strftime(self.format),
                "data": [
                    {
                        "id": self.fee.id,
                        "name": self.fee.name,
                        "value": format(self.fee.value, ".2f"),
                        "feeTaxType": models.AdditionalFee.FeeTypes(
                            self.fee.fee_tax_type
                        ).pretty_name,
                        "optional": self.fee.optional,
                        "taxable": self.fee.taxable,
                        "refundable": self.fee.refundable,
                        "calculationMethod": choices.CalculationMethod(
                            self.fee.calculation_method
                        ).pretty_name,
                    }
                ],
            },
        )

    def test_availability_calendar(self):
        with self.subTest("Custom count"):
            resp = self.api_client.get(
                "/api/v1/properties/{prop_id}/availability_calendar/?count=3".format(
                    prop_id=self.prop.id
                )
            )

            self.assertEqual(resp.status_code, 200)
            resp_json = resp.json()
            today = date.today()
            self.assertDictEqual(
                resp_json,
                {
                    "calendar": [
                        {
                            "available": True,
                            "date": str(today),
                            "minNights": MIN_NIGHTS,
                            "price": NIGHTLY_PRICE,
                            "priceFormatted": NIGHTLY_PRICE_STR,
                        },
                        {
                            "available": True,
                            "date": str(today + timedelta(days=1)),
                            "minNights": MIN_NIGHTS,
                            "price": NIGHTLY_PRICE,
                            "priceFormatted": NIGHTLY_PRICE_STR,
                        },
                        {
                            "available": True,
                            "date": str(today + timedelta(days=2)),
                            "minNights": MIN_NIGHTS,
                            "price": NIGHTLY_PRICE,
                            "priceFormatted": NIGHTLY_PRICE_STR,
                        },
                    ],
                    "count": "3",
                    "currency": "USD",
                },
            )

        with self.subTest("default count"):
            resp = self.api_client.get(
                "/api/v1/properties/{prop_id}/availability_calendar/".format(prop_id=self.prop.id)
            )

            self.assertEqual(resp.status_code, 200)

            resp_json = resp.json()
            self.assertEqual(len(resp_json["calendar"]), 180)

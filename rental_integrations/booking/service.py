import logging
import urllib
from unittest.mock import Mock

from lxml import etree

from rental_integrations.models import RawResponse
from rental_integrations.service import RentalAPIClient
from . import service_models, service_serializers
from .mappings import cozmo_to_booking

logger = logging.getLogger(__name__)


class BookingXmlClient(RentalAPIClient):

    _supply_url = "https://supply-xml.booking.com/"

    def __init__(self, user, secret):
        self._user = etree.Element("username")
        self._user.text = user
        self._password = etree.Element("password")
        self._password.text = secret

    @property
    def netloc(self):
        return self._supply_url

    def get_listing(self, code):
        url = urllib.parse.urljoin(self.netloc, "hotels/ota/OTA_HotelDescriptiveInfo")
        request = etree.Element("OTA_HotelDescriptiveInfoRQ")
        func = etree.SubElement(request, "HotelDesecriptiveInfos")
        model = etree.SubElement(func, "HotelDescriptiveInfo", HotelCode=code)
        status, content = self._call_api(url, data=request, http_method="post")
        return model

    def get_listings(self):
        """Retrieve all listings-related information."""
        url = urllib.parse.urljoin(self.netloc, "hotels/ota/OTA_HotelSearch")
        request = etree.fromstring(
            b"""<OTA_HotelSearchRQ xmlns="http://www.opentravel.org/OTA/2003/05" Version="2.001">
                <Criteria><Criterion/></Criteria>
            </OTA_HotelSearchRQ>"""
        )
        status, content = self._call_api(url, data=request, http_method="post")

        try:
            xml_search_rs = etree.fromstring(content)
            xml_properties = xml_search_rs.findall(".//Property", namespaces=xml_search_rs.nsmap)
            properties = service_serializers.PropertySearchSerializer(
                instance=xml_properties, many=True
            ).data
        except ValueError:
            logger.warn("Could not parse XML: %s", content)
            properties = []
        finally:
            RawResponse.objects.create(content=content, user=self._user.text)

        return status, properties

    def get_reservations(self, listing_id=None):
        """
        Retrieve reservations of a chosen or all listings (hotels, as booking.com calls them).

        If `listing_id` is given, only fetch reservations of this listing.
        """
        url = "https://secure-supply-xml.booking.com/hotels/xml/reservations"
        request = etree.fromstring(b'<?xml version="1.0" encoding="UTF-8"?><request></request>')

        if listing_id:
            hotel_id = etree.SubElement(request, "hotel_id")
            hotel_id.text = listing_id

        status, content = self._call_api(url, data=request, http_method="post")

        try:
            xml_reservations = etree.fromstring(content).xpath("./reservation")
            reservations = service_serializers.ReservationSerializer(
                instance=xml_reservations, many=True
            ).data
        except ValueError:
            logger.warn("Could not parse XML: %s", content)
            reservations = []
        finally:
            RawResponse.objects.create(content=content, user=self._user.text)
        return status, reservations

    def push_listing(self, prop: "listings.models.Property"):
        url = urllib.parse.urljoin(self.netloc, "hotels/ota/OTA_HotelDescriptiveContentNotif")
        data = BookingParser.to_booking(prop)

        request = etree.fromstring(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<OTA_HotelDescriptiveContentNotifRQ xmlns="http://www.opentravel.org/OTA/2003/05"'
            ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" PrimaryLangID="en-us"'
            ' EchoToken="GUID" TimeStamp="2015-06-09T09:30:47Z"'
            ' xsi:schemaLocation="http://www.opentravel.org/2014B/OTA_HotelDescriptiveContentNotifRQ.xsd"'  # noqa: E501
            ' id="OTA2014B" Version="8.0" Target="Test">'
            "    <HotelDescriptiveContents></HotelDescriptiveContents>"
            "</OTA_HotelDescriptiveContentNotifRQ>"
        )
        request.append(data)

        status, content = self._call_api(url, request, http_method="post")
        return status, etree.fromstring(content)

    def set_listing_details(self, listing_id, data):
        """
        Set availability, pricing, and other information for a given room.

        User can set period of [from_date, to_date) or specify list of dates, up to 3 years
        in the future.
        """
        request = etree.fromstring(b'<?xml version="1.0" encoding="UTF-8"?><request></request>')
        version = etree.SubElement(request, "version")
        version.text = "1.0"

        ser = service_serializers.AvailabilitySerializer(
            data={"room_id": listing_id, "dates": data["dates"]}
        )
        ser.is_valid(raise_exception=True)
        room = ser.save()
        request.append(room)

        url = urllib.parse.urljoin(self.netloc, "hotels/xml/availability")
        status, content = self._call_api(url, request, http_method="post")

        return status, etree.fromstring(content)

    def _authenticate(self, data, headers, context=None):
        data.append(self._user)
        data.append(self._password)
        if "/ota/" in (context or {}).get("url", ""):
            auth = (self._user, self._password)
        else:
            auth = None
        return auth

    def _parse_data(self, data):
        return etree.tostring(data)


class BookingParser:
    @staticmethod
    def to_cozmo(data: etree.Element) -> dict:
        pass  # TODO

    @staticmethod
    def to_booking(prop: "listings.models.Property") -> etree.Element:
        safe = {
            attr: getattr(prop, attr) or Mock(spec=keys, **dict.fromkeys(keys))
            for attr, keys in {
                "location": ["country", "city", "postal_code", "latitude", "longitude"],
                "owner": ["first_name", "last_name", "email", "phone"],
            }.items()
        }

        contact_infos = [
            service_models.ContactInfo(
                Addresses=[
                    service_models.ContactInfo.Address(
                        HotelName=prop.name,
                        AddressLine=prop.full_address,
                        CityName=safe["location"].city,
                        PostalCode=safe["location"].postal_code,
                        CountryName=safe["location"].country,
                    )
                ]
            ),
            service_models.ContactInfo(
                Names=[
                    service_models.ContactInfo.Name(
                        GivenName=safe["owner"].first_name, Surname=safe["owner"].last_name
                    )
                ],
                Emails=[service_models.ContactInfo.Email(value=safe["owner"].email)],
                Phones=[
                    service_models.ContactInfo.Phone(
                        attributes={"PhoneNumber": safe["owner"].phone, "PhoneTechType": "1"}
                    )
                ],
            ),
        ]
        hotel_info = service_models.HotelInfoXml(
            CategoryCodes=service_models.CategoryCodesXml(
                GuestRoomInfo=service_models.CategoryCodesXml.GuestRoomInfoXml(
                    attributes={"Quantity": str(prop.bedrooms)}
                ),
                HotelCategory=service_models.CategoryCodesXml.HotelCategoryXml(
                    attributes={"ExistsCode": "1", "Code": cozmo_to_booking[prop.property_type]}
                ),
            ),
            Position=service_models.HotelInfoXml.PositionXml(
                attributes={
                    "Latitude": safe["location"].latitude,
                    "Longitude": safe["location"].longitude,
                }
            ),
            OwnershipManagementInfos=[
                service_models.OwnershipManagementInfo(CompanyName=None)  # Independent property
            ],
        )
        multimedia = service_models.MultimediaDescription(
            ImageItems=[
                service_models.MultimediaDescription.ImageItem(
                    ImageFormat=service_models.ImageFormatXml(
                        URL=str(img.url), attributes={"Sort": i}
                    )
                )
                for i, img in enumerate(prop.image_set.self_hosted().only("url").order_by("order"))
            ]
        )

        return service_models.OTA_HotelDescriptiveContentNotifRQ(
            HotelDescriptiveContents=[
                service_models.HotelDescriptiveContent(
                    attributes={
                        "HotelName": prop.name,
                        "Language": "en",
                        "HotelDescriptiveContentNotifType": "New",
                    },
                    ContactInfos=contact_infos,
                    HotelInfo=hotel_info,
                    MultimediaDescriptions=[multimedia],
                )
            ]
        ).to_xml()

import inspect
from typing import List, Mapping, Text

import attr
from lxml import etree


class Attributes(Mapping):
    pass


class Value(Text):
    pass


@attr.s
class Xml:

    _attributes: Attributes = attr.ib(default={})
    _name = None
    _nsmap = None

    def _get_attributes(self):
        return {k: str(v) for k, v in self._attributes.items() if v is not None}

    def _get_name(self):
        return getattr(self, "_name") or type(self).__name__

    def to_xml(self):
        def _filter_members(member):
            return not inspect.isroutine(member) and not inspect.isclass(member)

        element = etree.Element(self._get_name(), attrib=self._get_attributes(), nsmap=self._nsmap)
        subelement_names = [
            name
            for name, value in inspect.getmembers(self, _filter_members)
            if not name.startswith("_") and value is not None
        ]
        element.text = getattr(self, "_", None)

        for name in subelement_names:
            subelement_value = getattr(self, name)
            if isinstance(subelement_value, list):
                subelement = etree.Element(name)
                subelement.extend(el.to_xml() for el in subelement_value)
            elif isinstance(subelement_value, Xml):
                subelement = subelement_value.to_xml()
            else:
                subelement = etree.Element(name)
                subelement.text = str(subelement_value)
            element.append(subelement)
        return element

    @classmethod
    def from_xml(cls, xml: etree._Element):
        kwargs = {}
        for attrib in attr.fields(cls):
            if attrib.type is None:
                continue
            elif issubclass(attrib.type, Xml):
                try:
                    child = xml.find(attrib.name)[0]
                    kwargs[attrib.name] = attrib.type.from_xml(child)
                except TypeError:
                    pass
            elif issubclass(attrib.type, Value):
                kwargs[attrib.name.lstrip("_")] = xml.text.strip()
            elif issubclass(attrib.type, str):
                kwargs[attrib.name] = xml.findtext(attrib.name, attrib.default, xml.nsmap)
            elif issubclass(attrib.type, List):
                child_type = attrib.type.__args__[0]
                kwargs[attrib.name] = [
                    child_type.from_xml(child)
                    for child in xml.findall(f"{attrib.name}/*", xml.nsmap)
                ]
            elif issubclass(attrib.type, Attributes):
                kwargs[attrib.name.lstrip("_")] = {
                    name: xml.get(name, default)
                    for name, default in attrib.default.items()
                    if name in xml.attrib
                }

        return cls(**kwargs)


@attr.s
class CategoryCodesXml(Xml):
    _name = "CategoryCodes"

    @attr.s
    class GuestRoomInfoXml(Xml):
        _attributes: Attributes = attr.ib(default={"Quantity": ""})
        _name = "GuestRoomInfo"

    @attr.s
    class HotelCategoryXml(Xml):
        _attributes: Attributes = attr.ib(default={"ExistsCode": "1", "Code": "20"})
        _name = "HotelCategory"

    GuestRoomInfo: GuestRoomInfoXml = attr.ib(default=None)
    HotelCategory: HotelCategoryXml = attr.ib(default=None)


@attr.s
class OwnershipManagementInfo(Xml):
    @attr.s
    class CompanyNameXml(Xml):
        _attributes: Attributes = attr.ib(default={"Code": ""})
        _name = "CompanyName"

    CompanyName: CompanyNameXml = attr.ib(default=None)


@attr.s
class HotelInfoXml(Xml):
    _name = "HotelInfo"

    @attr.s
    class PositionXml(Xml):
        _attributes: Attributes = attr.ib(default={"Latitude": "", "Longitude": ""})
        _name = "Position"

    CategoryCodes: CategoryCodesXml = attr.ib(default=None)
    Position: PositionXml = attr.ib(default=None)
    OwnershipManagementInfos: List[OwnershipManagementInfo] = attr.ib(default=[])


@attr.s
class ContactInfo(Xml):
    @attr.s
    class Address(Xml):
        _attributes: Attributes = attr.ib(default={"Language": None})
        HotelName: str = attr.ib(default="")
        AddressLine: str = attr.ib(default="")
        CityName: str = attr.ib(default="")
        PostalCode: str = attr.ib(default="")
        CountryName: str = attr.ib(default="")

    @attr.s
    class Name(Xml):
        _attributes: Attributes = attr.ib(default={"Language": None, "Gender": None})
        GivenName: str = attr.ib(default="")
        Surname: str = attr.ib(default="")
        JobTitle: str = attr.ib(default=None)

    @attr.s
    class Email(Xml):
        _value: Value = attr.ib(default="")

    @attr.s
    class Phone(Xml):
        _attributes: Attributes = attr.ib(default={"PhoneNumber": "", "PhoneTechType": "1"})

    _attributes: Attributes = attr.ib(default={"ContactProfileType": "PhysicalLocation"})

    Names: List[Name] = attr.ib(default=[])
    Addresses: List[Address] = attr.ib(default=[])
    Emails: List[Email] = attr.ib(default=[])
    Phones: List[Phone] = attr.ib(default=[])


@attr.s
class ImageFormatXml(Xml):
    _attributes: Attributes = attr.ib(default={"Sort": "", "Main": ""})
    URL: str = attr.ib(default="")


@attr.s
class MultimediaDescription(Xml):
    @attr.s
    class ImageItem(Xml):
        ImageFormat: ImageFormatXml = attr.ib(default=None)

    ImageItems: List[ImageItem] = attr.ib(default=[])


@attr.s
class HotelDescriptiveContent(Xml):
    _attributes: Attributes = attr.ib(
        default={"HotelName": "", "LanguageCode": "en", "HotelDescriptiveContentNotifType": "New"}
    )

    ContactInfos: List[ContactInfo] = attr.ib(default=[])
    HotelInfo: HotelInfoXml = attr.ib(default=None)
    MultimediaDescriptions: List[MultimediaDescription] = attr.ib(default=None)


@attr.s
class OTA_HotelDescriptiveContentNotifRQ(Xml):

    _xsi = "http://www.w3.org/2001/XMLSchema-instance"
    _nsmap = {None: "http://www.opentravel.org/OTA/2003/05", "xsi": _xsi}

    _attributes: Attributes = attr.ib(
        default={
            f"{{{_xsi}}}schemaLocation": "http://www.opentravel.org/2014B/OTA_HotelDescriptiveContentNotifRQ.xsd",  # noqa: E501
            "PrimaryLangID": "en-us",
            "EchoToken": "GUID",
            "TimeStamp": "2015-06-09T09:30:47Z",
            "id": "OTA2014B",
            "Version": "8.0",
            "Target": "Test",
        }
    )

    HotelDescriptiveContents: List[HotelDescriptiveContent] = attr.ib(default=[])

import json
from contextlib import suppress
from time import sleep

import requests
from django.conf import settings
from selenium.common.exceptions import NoSuchElementException

from rental_network.captcha import TwoCaptchaService
from rental_network.exceptions import ServiceException
from rental_network.service import RentalNetworkClient, TEMP_UPLOAD_FILE


class ZillowRentalNetworkClient(RentalNetworkClient):

    """
    Create account
     -

    Create listing
     - Setup webdriver
     - Go to website - https://www.zillow.com/
     - Login
        - Sign in
     - Create listing (split into multiple steps)
     - signout
     - Close

     Get listings
     - setup webdriver
     - go to website
     - Login
     - Get listings
     - Close
    """

    LISTINGS_URL = "https://www.zillow.com/rental-manager/proxy/rental-manager-api/api/v2/users/properties/listings"  # noqa: E501

    def is_authenticated(self):
        return self.driver.get_cookie("user_id") is not None

    def login(self):
        self.execute_nav(self.base_url)
        if "captchaPerimeterX" in self.driver.current_url:
            captcha_service = TwoCaptchaService(
                url=self.base_url,
                site_key=settings.ZILLOW_SITE_KEY,
                proxy=self.proxy.selenium_proxy().http_proxy,
            )
            # Add captcha token
            captcha_token = captcha_service.execute()
            self.execute_script("handleCaptcha('" + captcha_token + "');")
            # TODO verify that it moved on
        self.execute_click("//a[@class='znav-section-title']//span[contains(text(),'Sign in')]")
        self.execute_send_keys("//input[@id='reg-login-email']", self._user)
        self.execute_send_keys("//input[@id='inputs-password']", self._secret)
        self.execute_click("//input[@class='zsg-button_primary zsg-button_fullsize']")

    def _get_listings(self):
        cookies = {c["name"]: c["value"] for c in self.driver.get_cookies()}
        querystring = {
            "active": "true",
            "inactive": "true",
            "searchText": "",
            "feeds": "true",
            "manual": "true",
            "ascending": "true",
            "sort": "created",
            "featured": "all",
            "startKeyExclusive": "",
            "limit": "20",
            "includeListingDetails": "false",
            "includeListingRestrictions": "true",
            "includeMaintenancePartner": "true",
            "includeArchived": "false",
            "includeUnarchived": "true",
            "includePaidInclusionReleaseDates": "true",
        }

        headers = {
            "accept": "application/json,text/html",
            "rental_csrftoken": "66yrTNMy-sXgIYDp232NTrrn3G0nuAv_pfvk",
            "x-build-id": "1883",
            "x-newrelic-transaction": "https://www.zillow.com/rental-manager/proxy/rental-manager-api/api/v2/users/properties/listings",  # noqa: E501
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36",  # noqa: E501
            "cache-control": "no-cache",
        }
        response = requests.request(
            "GET", self.LISTINGS_URL, headers=headers, params=querystring, cookies=cookies
        )
        if response.ok and response.json() == 200:
            data = response.json().get("response")
            listings = data.get("listings", list())
            return listings
        raise ServiceException("Could not retrieve listings from Zillow account")

    @property
    def base_url(self):
        return "https://www.zillow.com"

    def get_listing(self, listing_id):
        pass

    def get_listings(self):
        """
        Response
        [{
            "listingId": "1wpdnqwpfqq5x_Postlets",
            "listingAlias": "2qtph4kpb4xac",
            "alias": 4539113690827779306,
            "aliasEncoded": "2qtph4kpb4xac",
            "name": "",
            "street": "1796 18th St",
            "city": "San Francisco",
            "unit": "",
            "state": "CA",
            "zip": "94107",
            "country": "",
            "geo": {"lat": 37.76255042587, "lon": -122.40022681789},
            "active": false,
            "dateCreated": "May 17, 2019 9:08:17 PM",
            "dateCreatedTimestamp": 1558141697848,
            "listingTypeCode": 5,
            "propertyTypeCode": 6,
            "isCommunity": false,
            "isMultifamily": false,
            "unitId": 2082863158,
            "contactEmail": "ivan@voyajoy.com",
            "contactPhone": "4156690356",
            "permanent": false,
            "dateUpdated": "May 17, 2019 9:34:22 PM",
            "dateUpdatedTimestamp": 1558143262281,
            "dateExpiration": "May 17, 2019 9:08:18 PM",
            "dateExpirationTimestamp": 1558141698262,
            "isPaidProperty": false,
            "feedName": "Zillow",
            "syndication": {
                "hotpads": {"status": "Syndication not attempted", "displayStatus": "Off Market"},
                "zillow": {"status": "Syndication not attempted", "displayStatus": "Off Market"},
                "trulia": {"status": "Syndication not attempted", "displayStatus": "Off Market"},
                "universal": {"message": ""},
            },
            "isViewable": true,
            "isEditable": true,
            "restrictions": {
                "isApplicationsRestricted": false,
                "isPaymentsRestricted": false,
                "isLeasesRestricted": true,
            },
            "floorPlanDetails": {
                "squareFeet": 100,
                "numBathrooms": 5.0,
                "numBedrooms": 0,
                "lowPrice": 1100.0,
            },
            "feedId": "Postlets",
            "feedListingId": "1wpdnqwpfqq5x",
        }]
        :return:
        """
        self.pre_execute()
        try:
            self.login()
            self.driver.get("https://www.zillow.com/rental-manager/properties")
            listings = self._get_listings()
            converted_listings = [
                {
                    "external_id": listing.get("listingId"),
                    "name": listing.get("name"),
                    "location": {
                        "address": listing.get("street"),
                        "city": listing.get("city"),
                        "apartment": listing.get("unit"),
                        "state": listing.get("state"),
                        "zipcode": listing.get("zip"),
                        "country": listing.get("country"),
                        "latitude": listing.get("geo").get("lat"),
                        "longitude": listing.get("geo").get("lon"),
                    },
                    "property_type": listing.get("propertyTypeCode"),
                    "listing_type": listing.get("listingTypeCode"),
                    "owner": {
                        "email": listing.get("contactEmail"),
                        "phone": listing.get("contactPhone"),
                    },
                    "bathrooms": listing.get("floorPlanDetails").get("numBathrooms"),
                    "bedrooms": listing.get("floorPlanDetails").get("numBedrooms"),
                    "pricing_settings": {
                        "monthly": listing.get("floorPlanDetails").get("lowPrice")
                    },
                    "raw": listing,
                }
                for listing in listings
            ]
            return converted_listings
        except Exception as e:
            pass
        self.post_execute()

    def create_listing(self, listing):  # noqa: C901
        listing_id = None
        self.pre_execute()
        try:
            self.login()
            self.execute_nav("https://www.zillow.com/rental-manager/properties")

            # Click " + Add a property"
            self.execute_click(
                "//a[@class='Link Link-secondary PropertyCard-heading-add-property']"
            )

            # Verify listing modal is displayed
            self.driver.find_element_by_xpath(
                "//div[@class='ReactModal__Content ReactModal__Content--after-open Modal AddPropertyModal']"  # noqa: E501
            ).is_displayed()

            # Type in address to "Property Address"
            self.execute_send_keys(
                "//div[@class='Autocomplete-InputContainer']//div//input[@class='Input']",
                listing.get("address"),
            )

            # Send "Unit number"
            # ac_list = self.driver.find_element_by_xpath(
            #     "//div[@class='Autocomplete-Result-List Autocomplete-Result-List-Modal']"
            # )
            self.execute_send_keys("//input[@placeholder='(Optional)']", listing.get("unit"))

            # Select "Property type"
            # select = self.driver.find_element_by_xpath("//select[@class='Select-element']")
            # options = select.find_elements_by_tag_name("option")
            # options[1].click()
            self.execute_click("//*[contains(text(), '{}')]".format(listing.get("property_type")))

            # Check "This is a room for rent with a shared living space"
            # self.execute_click"//div[@class='Checkbox-box']")

            # Click "Create my listing"
            self.execute_click("//button[@class='Button Button-primary Button-full']")

            details_page = self.driver.find_element_by_xpath(
                "//div[@class='Page Page-no-padding PropertyDetailsPage']"
            )
            details_page.is_displayed()
            # except:
            #     self.execute_nav("https://www.zillow.com/rental-manager/properties")
            # Get details page and verify displayed

            # Enter rent
            self.execute_send_keys(
                "//div[@class='PostingPath-margin-bottom']//input[@placeholder='Enter amount']",
                listing.get("price"),
                clear=True,
            )

            # enter lease duration
            """
            - 1 month
            - 6 months
            - 1 year
            - Rent to own
            - Sublet/temporary
            """
            self.execute_click("//*[contains(text(), '{}')]".format(listing.get("lease_duration")))

            # security deposit
            self.execute_send_keys(
                "//div[@class='Container ListingDetails']//div[@class='Col Col-md-6-12 PostingPath-Col-odd']//div[2]//div[1]//input[1]",  # noqa: E501
                listing.get("security_deposit"),
            )
            self.execute_click("//a[@class='Link Link-secondary PostingPath-link']")

            # date available
            self.execute_click("//a[contains(text(),'Set to available now')]")

            # select bed count
            """
            - Studio
            - 1, 2, 3, 4, 5, 6, 7, 8
            """
            self.execute_click(
                "//select[@name='beds']//option[contains(text(),'{}')]".format(
                    listing.get("bedrooms")
                )
            )

            # send lease terms
            self.execute_send_keys(
                "//input[@name='leaseTerms']", listing.get("lease_terms"), clear=True
            )

            # send bathrooms
            # 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5+
            self.execute_click(
                "//select[@name='baths']//option[contains(text(),'{}')]".format(
                    listing.get("bathrooms")
                )
            )

            # send descriptions
            self.execute_send_keys(
                "//textarea[@name='description']", listing.get("description"), clear=True
            )

            # send sqft
            self.execute_send_keys("//input[@placeholder='Square feet']", listing.get("sqft"))

            self.execute_click("//div[contains(text(),'Hide property address on listing')]")

            # for rent by
            self.execute_click("//div[contains(text(),'{}')]".format(listing.get("rent_by")))

            self.execute_script("document.getElementsByName('contactEmail')[0].value = ''")
            self.execute_send_keys(
                "//input[@name='contactEmail']", listing.get("contact_email", "ivan@voyajoy.com")
            )

            self.execute_script("document.getElementsByName('contactPhone')[0].value = ''")
            self.execute_send_keys(
                "//input[@name='contactPhone']", listing.get("contact_phone", "4156690356")
            )

            # owner name - doing this last because Zillow will remove name after phone number entry
            self.execute_script("document.getElementsByName('contactName')[0].value = ''")
            self.execute_send_keys(
                "//input[@name='contactName']", listing.get("contact_full_name", "Voyajoy")
            )

            # Only for Property owner or tenant
            # self.execute_click("//div[@class='checkbox-hide-phone']//div[@class='Checkbox-box']")
            # sleep(2)

            amenities = listing.get("amenities")
            # amenities
            if amenities.get("ac"):
                self.execute_click("//div[contains(text(),'A/C')]")
            if amenities.get("balcony"):
                self.execute_click("//div[contains(text(),'Balcony / Deck')]")
            if amenities.get("furnished"):
                self.execute_click("//div[contains(text(),'Furnished')]")
            if amenities.get("hardwood_floor"):
                self.execute_click("//div[contains(text(),'Hardwood Floor')]")
            if amenities.get("wheelchair_access"):
                self.execute_click("//div[contains(text(),'Wheelchair Access')]")
            if amenities.get("garage_parking"):
                self.execute_click("//div[contains(text(),'Garage Parking')]")
            if amenities.get("off_street_parking"):
                self.execute_click("//div[contains(text(),'Off-street Parking')]")

            # laundry (select one only)
            if amenities.get("laundry"):
                self.execute_click("//div[contains(text(),'Shared / In-building')]")
            else:
                self.execute_click("//div[contains(text(),'None')]")
                # self.execute_click("//div[contains(text(),'In unit')]")

            # pets
            if amenities.get("pets"):
                # or select one
                self.execute_click("//div[contains(text(),'Cats ok')]")
                self.execute_click("//div[contains(text(),'Small dogs ok')]")
                self.execute_click("//div[contains(text(),'Large dogs ok')]")
            else:
                self.execute_click("//div[contains(text(),'No pets allowed')]")

            self.execute_scroll_bottom()

            # photos
            for photo in listing.get("photos"):
                img = photo.url.read()
                if not img:
                    continue
                with open(TEMP_UPLOAD_FILE, "wb") as f:
                    f.write(img)
                    self.execute_upload("//input[@name='sourceFile']")

            # submit changes
            self.execute_click("//button[@class='Button Button-primary']")
            sleep(10)
            entries = self.proxy.har["log"]["entries"]
            response = list(
                filter(
                    lambda x: x,
                    [
                        x["response"]["content"]["text"]
                        if "properties/details" in x["request"]["url"]
                        else None
                        for x in entries
                    ],
                )
            )[0]
            resp = json.loads(response)
            if resp.get("httpStatus") == 200:
                listing_id = resp.get("response")["listingId"]

        except Exception as e:
            pass
        finally:
            self.post_execute()
        return listing_id

    def _is_listing_details_request(self, req, listing_id):
        return f"properties/details?propertyId={listing_id}" in req["request"]["url"]

    def update_listing(self, listing_id, listing):  # noqa: C901
        """
        Unable to update the following fields
         - Address
         - Unit
         - Property Type
        """
        self.pre_execute()
        try:
            self.login()
            self.execute_nav(
                f"https://www.zillow.com/rental-manager/properties/{listing_id}/listing"
            )

            entries = self.proxy.har["log"]["entries"]
            response = list(
                filter(
                    lambda x: x,
                    [
                        x["response"] if self._is_listing_details_request(x, listing_id) else None
                        for x in entries
                    ],
                )
            )

            if not response:
                raise ServiceException("No property details response")

            data = json.loads(response[0]["content"]["text"])
            prop_info = data.get("response")
            # Enter rent
            self.execute_send_keys(
                "//div[@class='PostingPath-margin-bottom']//input[@placeholder='Enter amount']",
                listing.get("price"),
                clear=True,
            )

            # enter lease duration
            """
            - 1 month
            - 6 months
            - 1 year
            - Rent to own
            - Sublet/temporary
            """
            self.execute_click("//*[contains(text(), '{}')]".format(listing.get("lease_duration")))

            # Security deposit
            self.execute_send_keys(
                "//div[@class='Container ListingDetails']//div[@class='Col Col-md-6-12 PostingPath-Col-odd']//div[2]//div[1]//input[1]",  # noqa: E501
                listing.get("security_deposit"),
                clear=True,
            )
            # self.execute_click("//a[@class='Link Link-secondary PostingPath-link']")

            # date available TODO
            self.execute_click("//a[contains(text(),'Set to available now')]")

            # select bed count
            """
            - Studio
            - 1, 2, 3, 4, 5, 6, 7, 8
            """
            self.execute_click(
                "//select[@name='beds']//option[contains(text(),'{}')]".format(
                    listing.get("bedrooms")
                )
            )

            # Lease terms
            self.execute_send_keys(
                "//input[@name='leaseTerms']", listing.get("lease_terms"), clear=True
            )

            # Bathrooms
            # 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5+
            self.execute_click(
                "//select[@name='baths']//option[contains(text(),'{}')]".format(
                    listing.get("bathrooms")
                )
            )

            # Descriptions
            self.execute_script(
                "Array.from(document.getElementsByTagName('textarea')).filter(x => x.getAttribute('name')==='description')[0].value = ''"  # noqa: E501
            )
            self.execute_send_keys(
                "//textarea[@name='description']", listing.get("description"), clear=True
            )

            # send sqft
            self.execute_send_keys(
                "//input[@placeholder='Square feet']", listing.get("sqft"), clear=True
            )

            # Hide property address. Don't update this
            # self.execute_click("//div[contains(text(),'Hide property address on listing')]")

            # for rent by
            self.execute_click("//div[contains(text(),'{}')]".format(listing.get("rent_by")))

            self.execute_script("document.getElementsByName('contactEmail')[0].value = ''")
            self.execute_send_keys(
                "//input[@name='contactEmail']", listing.get("contact_email", "ivan@voyajoy.com")
            )

            self.execute_script("document.getElementsByName('contactPhone')[0].value = ''")
            self.execute_send_keys(
                "//input[@name='contactPhone']", listing.get("contact_phone", "4156690356")
            )

            self.execute_script("document.getElementsByName('contactName')[0].value = ''")
            self.execute_send_keys(
                "//input[@name='contactName']", listing.get("contact_full_name", "Voyajoy")
            )

            # Only for Property owner or tenant
            # self.execute_click("//div[@class='checkbox-hide-phone']//div[@class='Checkbox-box']")
            # sleep(2)

            amenities = listing.get("amenities")
            # amenities
            if (
                amenities.get("ac")
                and not prop_info.get("airConditioning")
                or not amenities.get("ac")
                and prop_info.get("airConditioning")
            ):
                self.execute_click("//div[contains(text(),'A/C')]")
            if (
                amenities.get("balcony")
                and not prop_info.get("balconyDeckPatioPorch")
                or not amenities.get("balcony")
                and prop_info.get("balconyDeckPatioPorch")
            ):
                self.execute_click("//div[contains(text(),'Balcony / Deck')]")
            if (
                amenities.get("furnished")
                and not prop_info.get("isFurnished")
                or not amenities.get("furnished")
                and prop_info.get("isFurnished")
            ):
                self.execute_click("//div[contains(text(),'Furnished')]")
            if (
                amenities.get("hardwood_floor")
                and not prop_info.get("hardwoodFloors")
                or not amenities.get("hardwood_floor")
                and prop_info.get("hardwoodFloors")
            ):
                self.execute_click("//div[contains(text(),'Hardwood Floor')]")
            if (
                amenities.get("wheelchair_access")
                and not prop_info.get("wheelchairAccess")
                or not amenities.get("wheelchair_access")
                and prop_info.get("wheelchairAccess")
            ):
                self.execute_click("//div[contains(text(),'Wheelchair Access')]")
            if (
                amenities.get("garage_parking")
                and not prop_info.get("garageParking")
                or not amenities.get("garage_parking")
                and prop_info.get("garageParking")
            ):
                self.execute_click("//div[contains(text(),'Garage Parking')]")
            if (
                amenities.get("off_street_parking")
                and not prop_info.get("offStreetParking")
                or not amenities.get("off_street_parking")
                and prop_info.get("offStreetParking")
            ):
                self.execute_click("//div[contains(text(),'Off-street Parking')]")

            # laundry (select one only)
            if amenities.get("laundry"):
                self.execute_click("//div[contains(text(),'Shared / In-building')]")
            else:
                self.execute_click("//div[contains(text(),'None')]")
                # self.execute_click("//div[contains(text(),'In unit')]")

            # pets TODO
            if amenities.get("pets"):
                # Select 'No pets allowed' to reset checkboxes
                self.execute_click("//div[contains(text(),'No pets allowed')]")
                self.execute_click("//div[contains(text(),'Cats ok')]")
                self.execute_click("//div[contains(text(),'Small dogs ok')]")
                self.execute_click("//div[contains(text(),'Large dogs ok')]")
            else:
                self.execute_click("//div[contains(text(),'No pets allowed')]")

            self.execute_scroll_bottom()

            with suppress(NoSuchElementException):
                self.execute_click("//div[contains(@class, 'Action Action-close')]")

            # photos
            for photo in listing.get("photos"):
                img = photo.url.read()
                if not img:
                    continue
                with open(TEMP_UPLOAD_FILE, "wb") as f:
                    f.write(img)
                    self.execute_upload("//input[@name='sourceFile']")

            # submit changes
            # self.execute_click("//button[@class='Button Button-primary']")
            # entries = self.proxy.har['log']['entries']
            # response = list(filter(lambda x: x, [
            #     x["response"]["content"]["text"] if "properties/details" in x["request"][
            #         "url"] else None
            #     for x in entries]))[0]
            # resp = json.loads(response)
            # if resp.get("httpStatus") == 200:
            #     listing_id = resp.get("response")["listingId"]

        except Exception as e:
            pass
        finally:
            self.post_execute()
        return listing_id

    def get_contacts(self):
        pass

    def to_cozmo_property(self):
        pass

    def from_cozmo_property(self):
        pass

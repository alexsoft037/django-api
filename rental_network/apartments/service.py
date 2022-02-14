import json
from contextlib import suppress
from time import sleep

from django.conf import settings
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.keys import Keys

from rental_network.captcha import TwoCaptchaService
from rental_network.exceptions import ServiceException
from rental_network.models import Account
from rental_network.service import RentalNetworkClient, TEMP_UPLOAD_FILE


class ApartmentsRentalNetworkClient(RentalNetworkClient):

    LISTINGS_URL = ""

    def is_authenticated(self):
        return self.driver.get_cookie("user_id") is not None

    def login(self):
        self.execute_nav(self.base_url)
        self.execute_click("//a[@class='js-headerSignin headerSignIn']")
        self.driver.switch_to.frame(0)
        self.execute_send_keys("//input[@id='username']", self._user)
        self.execute_send_keys("//input[@id='password']", self._secret)
        self.execute_click("//button[@id='loginButton']")

    def _get_listings(self):
        pass

    @property
    def base_url(self):
        return "https://www.apartments.com"

    def get_listing(self, listing_id):
        self.pre_execute()
        try:
            self.login()
            self.execute_nav(
                f"https://www.apartments.com/add-edit-listing/?ListingKey={listing_id}"
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
            return data
        except Exception as e:
            pass

    def get_listings(self):
        pass

    def create_listing(self, listing):  # noqa: C901
        listing_id = None
        self.pre_execute()
        try:
            self.login()
            self.execute_click("//a[@id='headerAddListing']")
            address_xpath = "//input[@id='locationAddressLookup']"
            self.execute_send_keys(address_xpath, listing.get("address"))
            self.execute_send_keys(address_xpath, Keys.ARROW_DOWN)
            self.execute_send_keys(address_xpath, Keys.ENTER)
            self.execute_send_keys("//input[@id='locationUnitNumber']", listing.get("unit"))

            # Apartment, Condo, Townhome, Single Family Home
            self.execute_click(
                "//div[@class='radioGroup']//span[contains(text(),'{}')]".format(
                    listing.get("property_type")
                )
            )

            # Bedrooms
            self.execute_click(
                "//div[@class='btn-group bootstrap-select beds']//button[@class='btn dropdownToggle selectpicker btn-default']"  # noqa: E501
            )
            self.execute_click(
                "//div[@class='btn-group bootstrap-select beds']//span[@class='text'][contains(text(),'{}')]".format(  # noqa: E501
                    listing.get("bedrooms")
                )
            )

            # Bathrooms
            self.execute_click(
                "//div[@class='btn-group bootstrap-select baths']//button[@class='btn dropdownToggle selectpicker btn-default']"  # noqa: E501
            )
            self.execute_click(
                "//div[@class='btn-group bootstrap-select baths']//span[@class='text'][contains(text(),'{}')]".format(  # noqa: E501
                    listing.get("bathrooms")
                )
            )

            size_xpath = "//input[@id='sf-clone']"
            self.execute_clear(size_xpath)
            self.execute_click(size_xpath)
            self.execute_send_keys(size_xpath, listing.get("sqft"))

            if listing.get("floor"):
                self.execute_send_keys("//input[@id='floor-clone']", listing.get("floor"))
            self.execute_send_keys("//input[@id='rent-clone']", listing.get("price"))
            self.execute_send_keys("//input[@id='deposit-clone']", listing.get("security_deposit"))
            # TODO available

            lease_length_xpath = "//input[@id='leaselength-clone']"
            self.execute_clear(lease_length_xpath)
            self.execute_click(lease_length_xpath)
            self.execute_send_keys(lease_length_xpath, listing.get("lease_duration"))

            # I am an Owner, I am an Agent / Broker, I am a Property Manager
            self.execute_click("//span[contains(text(),'{}')]".format(listing.get("rent_by")))

            self.execute_send_keys(
                "//input[@id='firstname']", listing.get("contact_first_name", "Ivan"), clear=True
            )
            self.execute_send_keys(
                "//input[@id='lastname']", listing.get("contact_last_name", "Thai"), clear=True
            )
            self.execute_send_keys(
                "//input[@id='email']",
                listing.get("contact_email", "ivan+apartments@voyajoy.com"),
                clear=True,
            )
            self.execute_send_keys(
                "//input[@id='phone-clone']",
                listing.get("contact_phone", "4156690356"),
                clear=True,
            )

            self.execute_click("//span[contains(text(),'Hide my name on Apartments.com')]")
            self.execute_click(
                "//div[contains(@class,'btn-group bootstrap-select contactpreference')]//button[contains(@class,'btn dropdownToggle selectpicker btn-default')]"  # noqa: E501
            )
            self.execute_click(
                "//span[contains(text(),'{}')]".format(listing.get("contact_preference"))
            )

            for photo in listing.get("photos"):
                img = photo.url.read()
                if not img:
                    continue
                with open(TEMP_UPLOAD_FILE, "wb") as f:
                    f.write(img)
                    self.execute_upload(
                        "//div[contains(@class,'noPhotos')]//span//input[contains(@name,'files[]')]"  # noqa: E501
                    )

            self.execute_send_keys(
                "//div[contains(@class,'descriptionAmenitiesWrapper')]//textarea[@id='description']",  # noqa: E501
                listing.get("description"),
            )

            # Amenities
            amenities = listing.get("amenities")
            if amenities.get("pets"):
                # or select one
                self.execute_click("//span[contains(text(),'Dogs OK')]")
                self.execute_click("//span[contains(text(),'Cats OK')]")
            else:
                self.execute_click("//span[contains(text(),'No Pets')]")

            if amenities.get("furnished"):
                self.execute_click("//span[contains(text(),'Furnished')]")

            if amenities.get("smoking"):
                self.execute_click("//span[contains(text(),'No smoking')]")

            if amenities.get("wheelchair_access"):
                self.execute_click("//span[contains(text(),'Wheelchair Access')]")

            self.execute_click(
                "//div[contains(@class,'btn-group bootstrap-select gated')]//button[contains(@class,'btn dropdownToggle selectpicker btn-default')]"  # noqa: E501
            )
            self.execute_click(
                "//span[contains(@class,'text')][contains(text(),'{}')]".format(
                    "Yes" if amenities.get("gated") else "No"
                )
            )

            if amenities.get("laundry"):
                self.execute_click(
                    "//div[contains(@class,'btn-group bootstrap-select laundry')]//button[contains(@class,'btn dropdownToggle selectpicker btn-default')]"  # noqa: E501
                )
                self.execute_click("//span[contains(@class,'text')][text()='Washer/Dryer']")
                # Washer/Dryer Hookup, Laundry Facilities

            if amenities.get("parking"):
                self.execute_click(
                    "//div[contains(@class,'btn-group bootstrap-select parking')]//button[contains(@class,'btn dropdownToggle selectpicker btn-default')]"  # noqa: E501
                )
                # Surface Lot, Covered, Street, Garage, Other
                self.execute_click("//span[contains(@class,'text')][contains(text(),'Street')]")

            # Parking fee, only if parking is provided
            if listing.get("parking_fee"):
                self.execute_send_keys(
                    "//input[@id='parkingFee-clone']", listing.get("parking_fee")
                )

            # Agree to terms
            self.execute_click("//input[@id='agreeToTerms']")

            # Captcha
            captcha_service = TwoCaptchaService(
                url=self.base_url,
                site_key=settings.APARTMENTS_SITE_KEY,
                proxy=self.proxy.selenium_proxy().http_proxy,
            )
            # Add captcha token
            captcha_token = captcha_service.execute()
            self.execute_script(
                "grecaptcha.getResponse = function(y) { return '" + captcha_token + "'}"
            )

            # Submit changes
            self.execute_click("//button[@id='headerSubmit']")

            # Verification
            iframes = self.driver.find_elements_by_tag_name("iframe")
            iframe = list(filter(lambda x: "iFrameResizer" in x.get_attribute("id"), iframes))[0]
            self.driver.switch_to_frame(iframe)

            # Request sms code
            self.execute_click("//input[@id='sms']/..")
            self.execute_click("//button[@id='changeSubmit']")

            sleep(60)
            account = Account.objects.get(
                username=self._user, account_type=Account.AccountType.APARTMENTS.value
            )
            code = account.last_verification_code

            self.driver.switch_to_default_content()
            iframes = self.driver.find_elements_by_tag_name("iframe")
            iframe = list(filter(lambda x: "iFrameResizer" in x.get_attribute("id"), iframes))[0]
            self.driver.switch_to_frame(iframe)
            self.execute_send_keys("//input[@id='code']", code)

            self.execute_click("//button[@id='changeSubmit']")
            sleep(5)
            entries = self.proxy.har["log"]["entries"]
            response = list(
                filter(
                    lambda x: x,
                    [
                        x["response"]["content"]["text"]
                        if "basic/save" in x["request"]["url"]
                        else None
                        for x in entries
                    ],
                )
            )[0]
            resp = json.loads(response)
            if resp.get("Succeeded"):
                listing_id = resp.get("ListingKey")

        except Exception as e:
            pass
        finally:
            self.post_execute()
        return listing_id

    def _is_listing_details_request(self, req, listing_id):
        return (
            "basic/id" in req["request"]["url"]
            and req["request"]["method"] == "POST"
            and req["request"]["postData"]["text"] == '{"ListingKey":"' + listing_id + '"}'
        )

    def update_listing(self, listing_id, listing):  # noqa: C901
        """
        Can't change the following fields
         - Address
         - Listing Type
        """
        self.pre_execute()
        try:
            self.login()
            self.execute_nav(
                f"https://www.apartments.com/add-edit-listing/?ListingKey={listing_id}"
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
            prop_info = data.get("PropertyTypeInfo")
            prop_basics = prop_info.get("Basics")
            # if listing.get("bedrooms") != prop_basics.get("BedType"):
            self.execute_click(
                "//div[@class='btn-group bootstrap-select beds']//button[@class='btn dropdownToggle selectpicker btn-default']"  # noqa: E501
            )
            self.execute_click(
                "//div[@class='btn-group bootstrap-select beds']//span[@class='text'][contains(text(),'{}')]".format(  # noqa: E501
                    listing.get("bedrooms")
                )
            )

            # if listing.get("bathrooms") != prop_basics.get("BathType"):
            # bath_element = self.driver.find_element_by_xpath("//div[@class='btn-group bootstrap-select baths']//button[@class='btn dropdownToggle selectpicker btn-default']")  # noqa: E501
            self.execute_click(
                "//div[@class='btn-group bootstrap-select baths']//button[@class='btn dropdownToggle selectpicker btn-default']"  # noqa: E501
            )
            # bath_element.find_element_by_xpath("//span[@class='text'][contains(text(),'{}')]".format(listing.get("bathrooms")))  # noqa: E501
            self.execute_click(
                "//div[@class='btn-group bootstrap-select baths']//span[@class='text'][contains(text(),'{}')]".format(  # noqa: E501
                    listing.get("bathrooms")
                )
            )

            # if listing.get("sqft") != prop_basics.get("SquareFeet"):
            size_xpath = "//input[@id='sf-clone']"
            self.execute_clear(size_xpath)
            self.execute_click(size_xpath)
            self.execute_send_keys(size_xpath, listing.get("sqft"))

            # if float(listing.get("price")) != prop_basics.get("Rent"):
            rent_xpath = "//input[@id='rent-clone']"
            self.execute_clear(rent_xpath)
            self.execute_send_keys(rent_xpath, listing.get("price"))

            # if float(listing.get("security_deposit")) != prop_basics.get("Deposit"):
            deposit_xpath = "//input[@id='deposit-clone']"
            self.execute_clear(deposit_xpath)
            self.execute_send_keys(deposit_xpath, listing.get("security_deposit"))

            # TODO available

            # if listing.get("lease_duration") != prop_basics.get("LeaseLength").split(" ")[0]:
            lease_length_xpath = "//input[@id='leaselength-clone']"
            self.execute_clear(lease_length_xpath)
            self.execute_click(lease_length_xpath)
            self.execute_send_keys(lease_length_xpath, listing.get("lease_duration"))

            # photo_collection = data.get("PhotoInfo").get("PhotoCollection")

            with suppress(NoSuchElementException):
                self.execute_click("//span[@class='delete']")

            for photo in listing.get("photos"):
                img = photo.url.read()
                if not img:
                    continue
                with open(TEMP_UPLOAD_FILE, "wb") as f:
                    f.write(img)
                    self.execute_upload(
                        "//div[contains(@class,'noPhotos')]//span//input[contains(@name,'files[]')]"  # noqa: E501
                    )

            # I am an Owner, I am an Agent / Broker, I am a Property Manager
            self.execute_click("//span[contains(text(),'{}')]".format(listing.get("rent_by")))

            self.execute_send_keys(
                "//input[@id='firstname']", listing.get("contact_first_name", "Ivan"), clear=True
            )
            self.execute_send_keys(
                "//input[@id='lastname']", listing.get("contact_last_name", "Thai"), clear=True
            )
            self.execute_send_keys(
                "//input[@id='email']",
                listing.get("contact_email", "ivan+apartments@voyajoy.com"),
                clear=True,
            )
            self.execute_send_keys(
                "//input[@id='phone-clone']",
                listing.get("contact_phone", "4156690356"),
                clear=True,
            )

            # Don't change this
            # self.execute_click("//span[contains(text(),'Hide my name on Apartments.com')]")

            self.execute_click(
                "//div[contains(@class,'btn-group bootstrap-select contactpreference')]//button[contains(@class,'btn dropdownToggle selectpicker btn-default')]"  # noqa: E501
            )
            self.execute_click(
                "//div[contains(@class,'btn-group bootstrap-select contactpreference')]//span[@class='text'][contains(text(),'{}')]".format(  # noqa: E501
                    listing.get("contact_preference")
                )
            )

            self.execute_send_keys(
                "//div[contains(@class,'descriptionAmenitiesWrapper')]//textarea[@id='description']",  # noqa: E501
                listing.get("description"),
                clear=True,
            )

            # Amenities
            prop_amenities = prop_basics.get("Amenities")
            amenities = listing.get("amenities")
            if amenities.get("pets") and prop_basics.get("NoPetsAllowed"):
                # or select one
                self.execute_click("//span[contains(text(),'Dogs OK')]")
                self.execute_click("//span[contains(text(),'Cats OK')]")
            elif not prop_basics.get("NoPetsAllowed"):
                self.execute_click("//span[contains(text(),'No Pets')]")

            # 266
            if (amenities.get("furnished") and 266 not in prop_amenities) or (
                not amenities.get("furnished") and 266 in prop_amenities
            ):
                self.execute_click("//span[contains(text(),'Furnished')]")

            # 285
            if (amenities.get("smoking") and 285 not in prop_amenities) or (
                not amenities.get("smoking") and 285 in prop_amenities
            ):
                self.execute_click("//span[contains(text(),'No smoking')]")

            # 291
            if (amenities.get("wheelchair_access") and 291 not in prop_amenities) or (
                not amenities.get("wheelchair_access") and 291 in prop_amenities
            ):
                self.execute_click("//span[contains(text(),'Wheelchair Access')]")

            # 112
            self.execute_click(
                "//div[contains(@class,'btn-group bootstrap-select gated')]//button[contains(@class,'btn dropdownToggle selectpicker btn-default')]"  # noqa: E501
            )
            self.execute_click(
                "//span[contains(@class,'text')][contains(text(),'{}')]".format(
                    "Yes" if amenities.get("gated") else "No"
                )
            )

            self.execute_click(
                "//div[contains(@class,'btn-group bootstrap-select laundry')]//button[contains(@class,'btn dropdownToggle selectpicker btn-default')]"  # noqa: E501
            )
            if amenities.get("laundry"):
                self.execute_click(
                    "//div[contains(@class,'btn-group bootstrap-select laundry')]//span[@class='text'][text()='Washer/Dryer']"  # noqa: E501
                )
            else:
                self.execute_click(
                    "//div[contains(@class,'btn-group bootstrap-select laundry')]//span[@class='text'][text()='Laundry Type']"  # noqa: E501
                )
                # Washer/Dryer (81), Washer/Dryer Hookup (82), Laundry Facilities (48)

            self.execute_click(
                "//div[contains(@class,'btn-group bootstrap-select parking')]//button[contains(@class,'btn dropdownToggle selectpicker btn-default')]"  # noqa: E501
            )
            if amenities.get("parking"):
                # Surface Lot, Covered, Street, Garage, Other
                self.execute_click(
                    "//div[contains(@class,'btn-group bootstrap-select parking')]//span[contains(@class,'text')][contains(text(),'Street')]"  # noqa: E501
                )
            else:
                self.execute_click(
                    "//div[contains(@class,'btn-group bootstrap-select parking')]//span[contains(@class,'text')][contains(text(),'Parking Type')]"  # noqa: E501
                )

            # Parking fee, only if parking is provided
            if listing.get("parking_fee"):
                self.execute_send_keys(
                    "//input[@id='parkingFee-clone']", listing.get("parking_fee"), clear=True
                )

            # Agree to terms
            self.execute_click("//input[@id='agreeToTerms']")

            # Submit changes
            self.execute_click("//button[@id='headerSubmit']")
        except Exception as e:
            pass

    def get_contacts(self):
        pass

    def to_cozmo_property(self):
        pass

    def from_cozmo_property(self):
        pass

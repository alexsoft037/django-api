import abc
import logging
import uuid
from time import sleep

import requests
from browsermobproxy import RemoteServer
from django.conf import settings
from selenium import webdriver
from selenium.webdriver import DesiredCapabilities
from selenium.webdriver.chrome.options import Options

from rental_network.exceptions import ServiceException

logger = logging.getLogger(__name__)


TEMP_UPLOAD_FILE = "/tmp/selenium_img.png"


class RentalNetworkClient(metaclass=abc.ABCMeta):

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

    def __init__(self, user: str, secret: str, proxy: str = "", hub_url: str = ""):
        self._user = user
        self._secret = secret
        self.proxy = proxy
        if hub_url:
            self.hub_url = hub_url
        else:
            self.hub_url = f"{settings.SELENIUM_HUB_URL}:{settings.SELENIUM_HUB_PORT}"
        self.driver = None
        self.screenshots = list()

    def check_status(self):
        resp = requests.get(f"{self.hub_url}/wd/hub/status")
        if resp.ok:
            data = resp.json()
            status = data.get("status")
            value = data.get("value")
            return status == 0 and value.get("ready") is True
        raise ServiceException()

    def pre_execute(self):
        self.driver = self.get_driver()

    def post_execute(self):
        if self.proxy:
            self.proxy.close()
        self.driver.close()

    def execute(self, f):
        self.pre_execute()
        f()
        self.post_execute()

    def get_driver(self):
        server = RemoteServer(host="76.103.90.181", port=5051)
        self.proxy = server.create_proxy()

        self.proxy.new_har("req", options={"captureHeaders": True, "captureContent": True})
        options = Options()
        options.add_argument("--window-size=1920,2880")
        options.add_argument("--ignore-certificate-errors")
        # options.add_argument("--user-data-dir=/tmp/aaa")
        # options.add_argument("--log-net-log=/tmp/aaa.json")
        # desired_capabilities = {"browserName": "chrome", "loggingPrefs": {"performance": "INFO"}}
        driver_data = dict(
            command_executor=f"http://{self.hub_url}/wd/hub",
            # command_executor="http://165.227.57.38:4444/wd/hub",
            desired_capabilities=DesiredCapabilities.CHROME,
            # service_log_path="/Users/ivanthai/Desktop/selenium.log",
            # desired_capabilities=desired_capabilities,
            options=options,
        )
        if self.proxy:
            # proxy_data = {
            #     # "httpProxy": "76.103.90.181:5050",
            #     "httpProxy": "76.103.90.181:8087",
            #     "httpsProxy": "76.103.90.181:8087",
            #     "sslProxy": "76.103.90.181:8087",
            #     # "httpProxy": self.proxy,
            #     # "httpsProxy": self.proxy,
            #     "proxyType": ProxyType.MANUAL
            # }
            # proxy = Proxy(proxy_data)
            driver_data.update(proxy=self.proxy.selenium_proxy())
        driver = webdriver.Remote(**driver_data)
        logger.debug(f"Created driver={driver}")
        driver.implicitly_wait(5)
        return driver

    def get_last_screenshot(self):
        return self.screenshots[-1] if self.screenshots else None

    def execute_screenshot(self):
        img_64 = self.driver.get_screenshot_as_file(f"{str(uuid.uuid4())}.png")
        # img_64 = self.driver.get_screenshot_as_base64()
        self.screenshots.append(img_64)

    def _pre_execute_step(self):
        """
        Verify
        Screenshot
        :return:
        """
        pass

    def _post_execute_step(self):
        """
        Verify for results
        Screenshot
        Pause
        :return:
        """
        self.execute_screenshot()
        sleep(1)

    def _execute(self, f, *args):
        self._pre_execute_step()
        f(*args)
        self._post_execute_step()

    def execute_action(self, action, *args, **kwargs):
        actions = {
            "click": self.execute_click,
            "script": self.execute_script,
            "scroll_bottom": self.execute_scroll_bottom,
            "upload": self.execute_upload,
            "nav": self.execute_nav,
            "clear": self.execute_clear,
            "send_keys": self.execute_send_keys,
        }
        action_function = actions.get(action)
        action_function(args, kwargs)

    def execute_click(self, xpath):
        self._execute(self._click, xpath)

    def _click(self, xpath):

        elements = self.driver.find_elements_by_xpath(xpath)
        for each in elements:
            each.click()

    def execute_script(self, script):
        self._execute(self._script, script)

    def _script(self, script):
        self.driver.execute_script(script)

    def execute_scroll_bottom(self):
        self._execute(self._scroll_bottom)

    def _scroll_bottom(self):
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

    def execute_upload(self, xpath):
        self._execute(self._upload, xpath)

    def _upload(self, xpath):
        self.driver.find_element_by_xpath(xpath).send_keys(TEMP_UPLOAD_FILE)

    def execute_nav(self, url):
        self._execute(self._nav, url)

    def _nav(self, url):
        self.driver.get(url)

    def execute_clear(self, xpath):
        self._execute(self._text_clear, xpath)

    def _text_clear(self, xpath):
        self.driver.find_element_by_xpath(xpath).clear()

    def execute_send_keys(self, xpath, text, clear=False, click_before=False):
        if clear:
            self.execute_clear(xpath)
        if click_before:
            self.execute_click(xpath)
        self._execute(self._send_keys, xpath, text)

    def _send_keys(self, xpath, text):
        self.driver.find_element_by_xpath(xpath).send_keys(text)

    @abc.abstractmethod
    def is_authenticated(self):
        pass

    @abc.abstractmethod
    def login(self):
        pass

    @property
    @abc.abstractmethod
    def base_url(self):
        pass

    @abc.abstractmethod
    def get_listing(self, listing_id):
        pass

    @abc.abstractmethod
    def get_listings(self):
        pass

    @abc.abstractmethod
    def create_listing(self, listing):
        pass

    @abc.abstractmethod
    def update_listing(self, listing_id, listing):
        pass

    def navigate_to_listings(self):
        self.driver.get("https://www.zillow.com/rental-manager/properties")

    def init_step(self):
        """
        Go to website
        :return:
        """
        pass

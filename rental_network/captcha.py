import abc
import logging
from time import sleep

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class BaseCaptchaService(metaclass=abc.ABCMeta):

    def __init__(self, url, site_key, proxy):
        self.url = url
        self.site_key = site_key
        self.proxy = proxy

    @abc.abstractmethod
    def execute(self):
        pass

    @property
    @abc.abstractmethod
    def api_key(self):
        pass


class TwoCaptchaService(BaseCaptchaService):
    CAPTCHA_URL = "http://2captcha.com/in.php?key={}&method=userrecaptcha&googlekey={}&pageurl={}"
    CAPTCHA_RESP_URL = "http://2captcha.com/res.php?key={}&action=get&id={}"

    def execute(self):
        proxy = {'http': 'http://' + self.proxy, 'https': 'https://' + self.proxy}
        s = requests.Session()
        captcha_id = s.post(
            self.CAPTCHA_URL.format(
                self.api_key, self.site_key, self.url), proxies=proxy).text.split('|')[1]

        recaptcha_answer = s.get(
            self.CAPTCHA_RESP_URL.format(self.api_key, captcha_id),
            proxies=proxy).text

        while 'CAPCHA_NOT_READY' in recaptcha_answer:
            sleep(5)
            recaptcha_answer = s.get(
                self.CAPTCHA_RESP_URL.format(self.api_key, captcha_id),
                proxies=proxy).text

        recaptcha_answer = recaptcha_answer.split('|')[1]
        return recaptcha_answer

    @property
    def api_key(self):
        return settings.TWO_CAPTCHA_API_KEY

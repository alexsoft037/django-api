from unittest import mock

from django.test import TestCase

from .storages import DOStorage

RELATIVE_URL = "/some/relative/file/"
RETURN_URL = "https://sfo2.digitaloceanspaces.com/cozmo-dev/cozmo/properties/\
1d5c3e09ec43b37fe6ea3fc9e35234ae.jpg?AWSAccessKeyId=QN6JB42DP7TMOSOT7RID&Signature=\
tqwYja980mDV4nDX7XFxT9zeuu4%3D&Expires=1552007303"


class DOStorageTestCase(TestCase):
    def setUp(self):
        self.storage = DOStorage()

    def assert_url_correct(self, relative):
        url = self.storage.url(relative)
        self.assertEquals(url, RETURN_URL)

    @mock.patch.object(DOStorage, "url", return_value=RETURN_URL)
    def test_url(self, mock_storage):
        with self.subTest(msg="Relative url"):
            self.assert_url_correct(RELATIVE_URL)

        with self.subTest(msg="Relative url without slash"):
            relative = RELATIVE_URL.lstrip("/")
            self.assert_url_correct(relative)

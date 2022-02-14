import os
import re
import uuid
from urllib.parse import urljoin

from azure.common import AzureMissingResourceHttpError
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from storages.backends import azure_storage
from storages.backends.s3boto3 import S3Boto3Storage, S3Boto3StorageFile


class CustomURLMixin:
    CDN_URL = settings.CDN_URL + "/{}"

    def url(self, name):
        """
        Return full URL for given name.

        Django generaly stores relative path to storages and prepends storage address
        before name. However User can manually store a full URL in DB. In such case
        do not prepend storage address.
        """
        if re.search(r"https?://", name):
            ret_url = name
        else:
            ret_url = self.CDN_URL.format(name)

        return ret_url


class AzureStorageFile(azure_storage.AzureStorageFile):
    def _get_file(self):
        try:
            f = super()._get_file()
        except AzureMissingResourceHttpError:
            f = ContentFile("")
        return f


class AzureStorage(CustomURLMixin, azure_storage.AzureStorage):
    def _open(self, name, mode="rb"):
        return AzureStorageFile(name, mode, self)


class DOStorageFile(S3Boto3StorageFile):
    def _get_file(self):
        try:
            f = super()._get_file()
        except Exception as e:
            f = ContentFile("")
        return f


class DOStorage(S3Boto3Storage):

    def _open(self, name, mode="rb"):
        name = self._normalize_name(self._clean_name(name))
        try:
            f = S3Boto3StorageFile(name, mode, self)
        except ClientError as err:
            # if err.response['ResponseMetadata']['HTTPStatusCode'] == 404:
            f = ContentFile("")
        return f

    def url(self, name, **kwargs):
        """
        Return full URL for given name.

        Django generaly stores relative path to storages and prepends storage address
        before name. However User can manually store a full URL in DB. In such case
        do not prepend storage address.
        """
        if re.search(r"https?://", name):
            ret_url = name
        else:
            ret_url = super().url(name, **kwargs)

        return ret_url


class DummyCDNStorage(FileSystemStorage):
    def url(self, name):
        """
        Return full URL for given name.

        Django generaly stores relative path to storages and prepends storage address
        before name. However User can manually store a full URL in DB. In such case
        do not prepend storage address.
        """
        ret_url = urljoin(self.location + "/", name)
        return ret_url


@deconstructible
class UploadImageTo(object):
    def __init__(self, sub_path):
        self.path = sub_path

    def __call__(self, instance, filename):
        _, ext = os.path.splitext(filename)
        file_name = str(uuid.uuid4())
        return os.path.join(self.path, f"{file_name}{ext.lower()}")

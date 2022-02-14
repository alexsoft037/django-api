from logging import getLogger

from django.contrib.auth.base_user import BaseUserManager

logger = getLogger(__name__)


class OwnerManager(BaseUserManager):

    def get_queryset(self):
        return super().get_queryset().filter(account_type="OW")

    def create(self, **kwargs):
        kwargs.update({"account_type": "OW"})
        return super().create(**kwargs)

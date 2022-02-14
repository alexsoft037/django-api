from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import JSONField
from django.db import models


User = get_user_model()


class DBDump(models.Model):

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    data = JSONField()
    date_updated = models.DateTimeField(auto_now=True, null=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)

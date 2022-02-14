import requests
from django.contrib.postgres.fields import JSONField
from django.db import models

from .mappers import Mapper

CATEGORIES_URL = (
    "https://www.yelp.com/developers/documentation/v3/all_category_list/categories.json"
)  # noqa


class YelpCategories(models.Model):
    """Categories from YELP"""

    name = models.CharField(max_length=50, unique=True, blank=False, null=False)
    category = JSONField(default={})

    @classmethod
    def fetch(cls):
        resp = requests.get(CATEGORIES_URL)
        resp.raise_for_status()

        for c in resp.json():
            cls.objects.update_or_create(name=c["alias"], defaults={"category": c})

    @classmethod
    def get_parent_category(cls, category):
        try:
            for key, cat in Mapper.categories.items():
                if category in cat.filter.split(","):
                    return key
            c = cls.objects.get(name=category)
            parents = c.category.get("parents")
            if parents:
                return cls.get_parent_category(parents[0])
            parent_category = Mapper.others.filter
        except YelpCategories.DoesNotExist:
            parent_category = Mapper.others.filter
        return parent_category

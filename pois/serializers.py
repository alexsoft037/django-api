import asyncio

import requests
from aiohttp import ServerTimeoutError
from django.conf import settings
from rest_framework import serializers

from .mappers import Mapper
from .services import yelp_business_api, yelp_search_api


class YelpBaseSerializer(serializers.Serializer):

    HTTP_TIMEOUT = 3
    TASK_EXPIRE = 4

    latitude = serializers.CharField()
    longitude = serializers.CharField()

    def create(self, validated_data):
        try:
            resp = requests.get(
                self.API_URL,
                params=validated_data,
                timeout=self.HTTP_TIMEOUT,
                headers={"Authorization": f"Bearer {settings.YELP_SECRET}"},
            )

            resp.raise_for_status()
            businesses = resp.json()["businesses"]
        except requests.HTTPError as e:
            raise serializers.ValidationError(e.response.content)

        return businesses


class YelpAutocompleteSerializer(YelpBaseSerializer):

    API_URL = "https://api.yelp.com/v3/autocomplete"

    text = serializers.CharField(max_length=50)

    def create(self, validated_data):
        businesses = super().create(validated_data)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        tasks = [asyncio.ensure_future(yelp_business_api(b["id"])) for b in businesses]

        try:
            businesses = loop.run_until_complete(asyncio.gather(*tasks))
        except ServerTimeoutError:
            businesses = (None,) * len(Mapper.categories)
        finally:
            loop.close()

        return businesses


class YelpSearchSerializer(YelpBaseSerializer):

    API_URL = "https://api.yelp.com/v3/businesses/search"
    HTTP_TIMEOUT = 8

    radius = serializers.IntegerField(required=False, min_value=1000, max_value=40000)
    term = serializers.CharField(max_length=50, required=False, allow_blank=True)
    limit = serializers.IntegerField(required=False, min_value=0, max_value=50, default=20)

    reviews = serializers.IntegerField(required=False, min_value=0)
    ratings = serializers.FloatField(required=False, min_value=0, max_value=5)

    def create(self, validated_data):
        reviews = validated_data.pop("reviews", 0)
        ratings = validated_data.pop("ratings", 0)

        businesses = super().create(validated_data)

        if reviews:
            businesses = (b for b in businesses if b["review_count"] >= reviews)
        if ratings:
            businesses = (b for b in businesses if b["rating"] >= ratings)

        return list(businesses)


class YelpTopPlacesSerializer(YelpBaseSerializer):

    radius = serializers.IntegerField(required=False, min_value=1000, max_value=40000)

    def _get_businesses(self, validated_data):
        search_params = {"limit": 3, **validated_data}

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        tasks = [
            asyncio.ensure_future(yelp_search_api({"categories": c.filter, **search_params}))
            for c in Mapper.categories.values()
        ]

        try:
            businesses = loop.run_until_complete(asyncio.gather(*tasks))
        except ServerTimeoutError:
            businesses = (None,) * len(Mapper.categories)
        finally:
            loop.close()

        return businesses

    def create(self, validated_data):

        businesses = self._get_businesses(validated_data)
        # Filter duplicates
        ids = []
        filtered_businesses = []
        for b in businesses:
            business = []
            if "businesses" in b:
                for val in b.get("businesses"):
                    id = val.get("id")
                    if id not in ids:
                        business.append(val)
                        ids.append(id)
            filtered_businesses.append(business)

        return dict(zip(Mapper.categories, filtered_businesses))

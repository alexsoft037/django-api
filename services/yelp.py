import logging

import requests
from django.conf import settings

from services.errors import ServiceError

logger = logging.getLogger(__name__)


class YelpService:
    URL = "https://api.yelp.com/v3/businesses/search"

    def __init__(self):
        self.token = settings.YELP_SECRET

    def _get_headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def get_recommendations(
        self, latitude, longitude, radius="10000", limit=1, sort_by="best_match"
    ):
        search_terms = [
            "restaurants",
            # 'parks',
            "hiking",
            "pubs",
            "nightlife",
            "coffee",
        ]
        results = dict()
        for term in search_terms:
            querystring = dict(
                radius=radius,
                longitude=longitude,
                latitude=latitude,
                term=term,
                limit=limit,
                sort_by=sort_by,
                # categories=list(),
                # open_now=False
            )
            response = self._make_request(querystring)
            if response:
                results[term] = self._extract_recommendation_results(response["businesses"])
        return results

    def _extract_recommendation_results(self, results_json):
        return [
            dict(
                categories=[x["alias"] for x in r["categories"]],
                rating=r["rating"],
                name=r["name"],
                url=r["url"],
                distance=r["distance"],
                phone=r["phone"],
                address=r["location"]["display_address"][0],
            )
            for r in results_json
        ]

    def _make_request(self, query):
        response = requests.get(self.URL, headers=self._get_headers(), params=query)
        if response.ok:
            return response.json()
        raise ServiceError("Unable to make request, status={}".format(response.status_code))

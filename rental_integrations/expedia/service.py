import json
import urllib

from requests.auth import HTTPBasicAuth

from rental_integrations.service import RentalAPIClient


class ExpediaProductAPIClient(RentalAPIClient):
    @property
    def netloc(self):
        return "https://services.expediapartnercentral.com/"

    def get_listings(self):
        url = urllib.parse.urljoin(self.netloc, "products/properties?limit=200")
        status, content = self._call_api(url, data={}, http_method="get")
        return status, content

    def get_reservations(self, listing_id=None):
        ...

    def set_listing_details(self, listing_id, data):
        ...

    def _authenticate(self, data, headers, context=None):
        return HTTPBasicAuth(self._user, self._secret)

    def _parse_data(self, data):
        return json.dumps(data).encode()

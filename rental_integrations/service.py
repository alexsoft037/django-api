import abc
import logging
from inspect import getargspec
from typing import Dict, List, Optional, Tuple, TypeVar, Union

import requests
from django.conf import settings

from listings.choices import PropertyTypes

logger = logging.getLogger(__name__)


Json = dict
Xml = TypeVar("Xml")
Payload = Union[Json, Xml]

HttpHeaders = Dict[str, str]
HttpStatus = int
Response = Tuple[HttpStatus, Payload]

HTTP_499_NOT_MY_FAULT = 499


class RentalAPIClient(metaclass=abc.ABCMeta):

    _http_methods = ("get", "post", "patch", "put", "delete", "options")
    features_map = {}
    property_types_map = {}
    timeout = 20

    def __init__(self, user: str, secret: str):
        self._user = user
        self._secret = secret

    def _call_api(self, url, data, http_method: Optional[str] = None) -> Optional[Response]:
        """Make an API call and return parsed response."""
        if http_method is None:
            http_method = "post"
        http_method = http_method.lower()

        if http_method not in self._http_methods:
            raise ValueError("Invalid HTTP method: {}".format(http_method))

        context = {"url": url, "http_method": http_method}

        headers = self.get_headers(context)
        auth = self._authenticate(data, headers, context=context)
        data = self._parse_data(data)

        logger.debug(f"method: {http_method}, data: {data}")
        try:
            resp = requests.request(
                http_method, url, data=data, headers=headers, auth=auth, timeout=self.timeout
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.info("Error while connecting to %s: %s", url, " ".join(e.args))
            return e.response.status_code, e.response.content

        logger.debug(f"status: {resp.status_code}")
        return resp.status_code, resp.content

    def get_headers(self, context):
        return {}

    def get_property_type(self, name):
        if name:
            return self.property_types_map.get(name, PropertyTypes.Other.pretty_name)
        return PropertyTypes.Condo.pretty_name

    # Abstract methods
    @property
    @abc.abstractmethod
    def netloc(self) -> str:
        """Base URL of API."""

    @abc.abstractmethod
    def get_listings(self) -> Response:
        """Retrieve all listings-related information."""

    @abc.abstractmethod
    def get_reservations(self, listing_id: str = None) -> Response:
        """Retrieve reservations of a chosen or all listings."""

    @abc.abstractmethod
    def set_listing_details(self, listing_id: str, data: List[dict]) -> Response:
        """Set availability, pricing, or other information for a given listing."""

    @abc.abstractmethod
    def _authenticate(
        self, data: Payload, headers: HttpHeaders, context=None
    ) -> requests.auth.AuthBase:
        """Add authentication data to payload if needed."""

    @abc.abstractmethod
    def _parse_data(self, data) -> bytes:
        """Prepares data from a custom format to `bytes` to be used as HTTP data."""

    def perform_check_request(self):
        """Send simple request to check if credentials are valid"""


class BaseService:
    """Legacy class."""

    http_method_names = ["GET", "POST", "PUT", "PATCH", "DELETE"]
    timeout = 5

    def __init__(
        self,
        access_token=None,
        username=None,
        password=None,
        auth_callback=None,
        verbose=False,
        **kwargs,
    ):
        assert username, "username is required parameter"
        self._access_token = access_token
        self._username = username
        self._password = password
        if auth_callback is None:
            auth_callback = self._dummy_callback
        elif not callable(auth_callback) or len(getargspec(auth_callback).args) != 1:
            raise ValueError("`auth_callback` should be a callable")
        self._auth_callback = auth_callback
        self._verbose = verbose
        self._extra_kwargs = kwargs

    def get_headers(self, headers=dict()) -> dict:
        """Get expected headers for the service."""
        raise NotImplementedError()

    def get_params(self, params=dict()) -> dict:
        """
        Return all the parameters (querystring) that should be used.

        Usually returns basic params + parameters.
        """
        raise NotImplementedError()

    def format_path(self, path, path_kwargs):
        """Format the path to a full URL."""
        raise NotImplementedError()

    def _dummy_callback(self, service):
        ...

    def _make_request(self, method, url, data=None, **kwargs):
        method = method.lower()
        if method not in ("get", "post", "put"):
            raise ValueError("Unsupported method {}".format({}))

        try:
            resp = requests.request(method, url, data=data, timeout=self.timeout, **kwargs)
        except requests.RequestException as e:
            logger.exception("Error handling request %s", url)
            resp = requests.Response()
            resp.url = url
            resp.status_code = HTTP_499_NOT_MY_FAULT

        logger.debug("Response %s: %s", resp.status_code, resp.text)

        if self._verbose or getattr(settings, "SERVICE_REQUEST_DEBUG", False):
            logger.debug(
                "%s to %s took %s seconds. %s, resp: %s",
                resp.request.method,
                resp.url,
                resp.elapsed.total_seconds(),
                resp,
                resp.json(),
            )

        return resp

    def _request(
        self,
        path,
        data=dict(),
        method="get",
        path_kwargs=dict(),
        headers=dict(),
        params=dict(),
        retry=True,
        **kwargs,
    ):
        """Prepare and perform a request to a service."""
        # Save original arguments to be used in case we need to retry after
        # authentication.
        original_kwargs = {
            "path": path,
            "data": data,
            "method": method,
            "path_kwargs": path_kwargs,
            "headers": headers,
            "params": params,
        }
        original_kwargs.update(original_kwargs)
        # parse arguments
        url = self.format_path(path, path_kwargs)
        logger.debug("%s request with %s at %s" % (method, data, url))
        kwargs["headers"] = self.get_headers(headers)
        kwargs["params"] = self.get_params(params)
        logger.debug("HEADERS %s PARAMS %s" % (kwargs["headers"], kwargs["params"]))

        resp = self._make_request(method, url, data, **kwargs)

        # If we received a 401 we need to log in and redo the request
        if self.need_to_auth(resp) and retry:
            auth_resp = self.authenticate(self._username, self._password)
            if auth_resp["success"]:
                self._access_token = auth_resp["data"]["access_token"]
            else:
                pass
            return self._request(retry=False, **original_kwargs)

        return resp

    def _post(self, path, **kwargs):
        kwargs["method"] = "post"
        return self._request(path, **kwargs)

    def _get(self, path, **kwargs):
        kwargs["method"] = "get"
        return self._request(path, **kwargs)

    def _put(self, path, **kwargs):
        kwargs["method"] = "put"
        return self._request(path, **kwargs)

    def authenticate(self, username, password):
        """
        Authenticate against the service.

        Should call self._auth_callback and return an access token.
        """
        raise NotImplementedError()

    def need_to_auth(self, resp):
        """Check response to see if a new authentication is required."""
        raise NotImplementedError()

    def get_session_info(self):
        """Get service information which will be later saved in Account entity."""
        raise NotImplementedError()

    def get_host_listings(self, offset=0, limit=50, has_availability=False) -> (list, dict):
        """Get all listings for given host."""
        raise NotImplementedError()

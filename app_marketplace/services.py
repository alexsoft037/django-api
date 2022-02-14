import base64
import email
import logging
from itertools import chain
from urllib.parse import urlencode

import httplib2
import requests
import stripe
from django.conf import settings
from googleapiclient.discovery import build as g_build
from googleapiclient.errors import HttpError as GoogleHttpError
from oauth2client.client import FlowExchangeError, OAuth2Credentials, flow_from_clientsecrets
from rest_framework.status import HTTP_404_NOT_FOUND

from . import exceptions

logger = logging.getLogger(__name__)


class Slack:

    CACHE_KEY = "slack_{}"
    SCOPES = "incoming-webhook"
    DEFAULT_ID = settings.SLACK_ID
    DEFAULT_SECRET = settings.SLACK_SECRET
    VERIFY_URL = "https://slack.com/api/oauth.access"
    INSTALL_URL = "https://slack.com/oauth/authorize?{query}"
    _http_timeout = 5

    def __init__(self, client_id=None, client_secret=None):
        self._client_id = client_id or self.DEFAULT_ID
        self._client_secret = client_secret or self.DEFAULT_SECRET

    def _call_api(self, method, url, **kwargs):
        resp = requests.request(method, url, timeout=self._http_timeout, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def verify_access(self, access_params) -> dict:
        url = self.VERIFY_URL
        access_params.update({"client_id": self._client_id, "client_secret": self._client_secret})

        try:
            access_data = self._call_api("get", url, params=access_params)
        except requests.HTTPError as e:
            content = getattr(e.response, "content", None)
            logger.info("Could not get data from Slack oauth.access: %s", content)
            access_data = {}
        except requests.Timeout:
            logger.info("Connection to %s timed out", url)
            access_data = {}
        return access_data

    def send_message(self, hook_url, text) -> bool:
        if not hook_url.startswith("https://hooks.slack.com/services/"):
            raise ValueError("Invalid hook_url")

        try:
            self._call_api(
                "post", hook_url, data={"text": text}, headers={"content-type": "application/json"}
            )
            ok = True
        except requests.HTTPError as e:
            if e.response.status_code == HTTP_404_NOT_FOUND:
                raise exceptions.SlackError(hook_url)
            ok = False
        except requests.Timeout:
            logger.info("Connection to %s timed out", hook_url)
            ok = False
        return ok

    @classmethod
    def install_url(cls, *, state, redirect_uri):
        return cls.INSTALL_URL.format(
            query=urlencode(
                {
                    "client_id": cls.DEFAULT_ID,
                    "state": state,
                    "scope": cls.SCOPES,
                    "redirect_uri": redirect_uri,
                }
            )
        )


class Google:

    CACHE_KEY = "google_{}"
    SCOPES = " ".join(
        [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/userinfo.email",
        ]
    )
    CLIENT_SECRET = "/etc/voyajoy/files/google_secret.json"

    def __init__(self, credentials: str = None):
        if credentials:
            self.credentials = OAuth2Credentials.from_json(credentials)

    @property
    def _service(self):
        attr_name = "_g_service"
        try:
            srv = getattr(self, attr_name)
        except AttributeError:
            srv = g_build(
                serviceName="gmail", version="v1", http=self.credentials.authorize(httplib2.Http())
            )
            setattr(self, attr_name, srv)
        return srv

    def verify_access(self, access_params):
        flow = flow_from_clientsecrets(
            self.CLIENT_SECRET, self.SCOPES, redirect_uri=access_params["redirect_uri"]
        )
        try:
            self.credentials = flow.step2_exchange(access_params["code"])
            user_info = (
                g_build(
                    serviceName="oauth2",
                    version="v2",
                    http=self.credentials.authorize(httplib2.Http()),
                )
                .userinfo()
                .get()
                .execute()
            )

            if not user_info or "id" not in user_info:
                raise ValueError("No user ID could be retrieved")

            access_data = {"user_id": user_info["id"], "credentials": self.credentials.to_json()}
        except (ValueError, FlowExchangeError, GoogleHttpError) as e:
            logger.info("An error occurred: %s", e)
            access_data = {}
        return access_data

    @classmethod
    def install_url(cls, *, state, redirect_uri):
        flow = flow_from_clientsecrets(cls.CLIENT_SECRET, cls.SCOPES, redirect_uri=redirect_uri)
        flow.params.update({"access_type": "offline", "approval_prompt": "force", "state": state})
        return flow.step1_get_authorize_url()

    def get_messages(self, user_id=None, query_params: dict = None):
        if user_id is None:
            user_id = "me"

        def _all_messages():
            response = {"nextPageToken": None}
            while "nextPageToken" in response:
                try:
                    response = (
                        self._service.users()
                        .messages()
                        .list(
                            userId=user_id,
                            pageToken=response["nextPageToken"],
                            q=self._parse_query(query_params),
                            fields="messages(id),nextPageToken",
                        )
                        .execute()
                    )
                    yield response["messages"]
                except (GoogleHttpError, KeyError):
                    return

        return (self.get_message(m["id"], user_id=user_id) for m in chain(*_all_messages()))

    def get_message(self, message_id, user_id=None):
        if user_id is None:
            user_id = "me"

        try:
            raw_message = (
                self._service.users()
                .messages()
                .get(userId=user_id, id=message_id, format="raw", fields="threadId,raw")
                .execute()
            )
            message = email.message_from_bytes(
                base64.urlsafe_b64decode(raw_message["raw"].encode("ascii"))
            )
        except GoogleHttpError:
            message = None

        return message

    def send_message(self, sender, to, subject, message_text: str, parent_message_id=None):
        """
        Send email on behalf of user.

        Args:
            sender: sender email address
            to: recipient email address
            subject: subject of email address
            message_text: text of email
            parent_message_id: value for 'In-Reply-To' and 'References' headers,
                might be needed by some email clients to correctly create email threads
        """
        message = email.message_from_string(message_text)
        message["to"] = to
        message["from"] = sender
        message["subject"] = subject

        if parent_message_id:
            message["In-Reply-To"] = parent_message_id
            message["References"] = parent_message_id

        try:
            resp = (
                self._service.users()
                .messages()
                .send(
                    userId="me",
                    body={"raw": base64.urlsafe_b64encode(bytes(message)).decode("utf8")},
                )
                .execute()
            )
        except GoogleHttpError:
            resp = None
        return resp

    def get_thread(self, thread_id, user_id=None):
        if user_id is None:
            user_id = "me"

        try:
            raw_thread = (
                self._service.users()
                .threads()
                .get(
                    userId=user_id,
                    id=thread_id,
                    fields="id,messages(id,payload(body,parts,headers,mimeType))",
                )
                .execute()
            )
        except GoogleHttpError:
            raw_thread = {}

        return [self._build_message(raw_msg) for raw_msg in raw_thread["messages"]]

    def get_threads(self, user_id=None, query_params: dict = None):
        if user_id is None:
            user_id = "me"

        def _all_threads():
            response = {"nextPageToken": None}
            while "nextPageToken" in response:
                try:
                    response = (
                        self._service.users()
                        .threads()
                        .list(
                            userId=user_id,
                            pageToken=response["nextPageToken"],
                            q=self._parse_query(query_params),
                            fields="threads(id),nextPageToken",
                        )
                        .execute()
                    )
                    yield response["threads"]
                except (GoogleHttpError, KeyError):
                    return

        return (self.get_thread(t["id"], user_id=user_id) for t in chain(*_all_threads()))

    def _build_message(self, raw_msg, skip_attachments=True):
        payload = raw_msg.get("payload", raw_msg)
        mime_type = payload["mimeType"]

        if mime_type in ("text/plain", "text/html"):
            mime_msg = email.message_from_bytes(
                base64.urlsafe_b64decode(payload["body"].get("data", b""))
            )
        elif mime_type in ("multipart/related", "multipart/alternative", "multipart/mixed"):
            mime_msg = email.mime.multipart.MIMEMultipart()
            for part in payload["parts"]:
                is_attachment = raw_msg.get("body", {}).get("attachmentId", None)
                if is_attachment and skip_attachments:
                    continue
                part_msg = self._build_message(part, skip_attachments=skip_attachments)
                mime_msg.attach(part_msg)
        else:
            mime_msg = email.message_from_bytes(b"")
            logger.info(
                "Error importing mime_type=%s, id=%s", mime_type, raw_msg.get("id", "unkown")
            )

        for header in payload["headers"]:
            mime_msg[header["name"]] = header["value"]

        return mime_msg

    def _parse_query(self, query_params: dict) -> str:
        if query_params:
            base_query = query_params.pop("query", "")
            additional_params = " ".join("{}:{}".format(k, v) for k, v in query_params.items())
            query = "{} {}".format(base_query, additional_params)
            query_params["query"] = base_query
        else:
            query = None
        return query


class Stripe(Slack):

    CACHE_KEY = "stripe_{}"
    SCOPES = "read_write"
    DEFAULT_ID = "ca_CeJ8VNFTVmbdZvTl2eHjAW1UeaIetXsW"
    DEFAULT_SECRET = settings.STRIPE_SECRET
    _http_timeout = 5

    @classmethod
    def install_url(cls, *, state, redirect_uri):
        install_url = "https://dashboard.stripe.com/oauth/authorize?{query}"
        return install_url.format(
            query=urlencode(
                {
                    "client_id": cls.DEFAULT_ID,
                    "state": state,
                    "scope": cls.SCOPES,
                    "redirect_uri": redirect_uri,
                    "response_type": "code",
                }
            )
        )

    def verify_access(self, access_params) -> dict:
        url = "https://connect.stripe.com/oauth/token"
        access_params.update(
            {
                "client_secret": self._client_secret,
                "code": access_params["code"],
                "grant_type": "authorization_code",
            }
        )

        try:
            access_data = self._call_api("post", url, json=access_params)
        except requests.HTTPError as e:
            content = getattr(e.response, "content", None)
            logger.info("Could not get data from Slack oauth.access: %s", content)
            access_data = {}
        except requests.Timeout:
            logger.info("Connection to %s timed out", url)
            access_data = {}
        return access_data

    def verify_event(self, payload: bytes, signature: str):
        try:
            event = stripe.Webhook.construct_event(
                payload, signature, settings.STRIPE_WEBHOOK_SIGNATURE
            )
        except stripe.error.SignatureVerificationError as e:
            raise exceptions.StripeError(e.args) from e
        return event


class MailChimp:

    CACHE_KEY = "mailchimp_{}"
    DEFAULT_ID = settings.MAILCHIMP_ID
    DEFAULT_SECRET = settings.MAILCHIMP_SECRET
    _http_timeout = 5

    def __init__(self, client_id=None, client_secret=None):
        self._client_id = client_id or self.DEFAULT_ID
        self._client_secret = client_secret or self.DEFAULT_SECRET

    @classmethod
    def install_url(cls, *, state, redirect_uri):
        install_url = "https://login.mailchimp.com/oauth2/authorize?{query}"
        return install_url.format(
            query=urlencode(
                {
                    "client_id": cls.DEFAULT_ID,
                    "redirect_uri": redirect_uri,
                    "response_type": "code",
                    "state": state,
                }
            )
        )

    def _call_api(self, method, url, **kwargs):
        resp = requests.request(method, url, timeout=self._http_timeout, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def verify_access(self, access_params) -> dict:
        url = "https://login.mailchimp.com/oauth2/token"
        access_params.update(
            {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "authorization_code",
            }
        )

        try:
            access_data = self._call_api("post", url, data=access_params)
        except requests.HTTPError as e:
            content = getattr(e.response, "content", None)
            logger.info("Could not get data from MailChimp oauth.access: %s", content)
            access_data = {}
        except requests.Timeout:
            logger.info("Connection to %s timed out", url)
            access_data = {}
        return access_data


class Airbnb(Slack):

    CACHE_KEY = "airbnb_{}"
    DEFAULT_ID = settings.AIRBNB_ID
    DEFAULT_SECRET = settings.AIRBNB_SECRET
    SCOPES = ",".join(["vr", "messages_read", "messages_write"])
    VERIFY_URL = "https://api.airbnb.com/v2/oauth2/authorizations?_unwrapped=true"
    INSTALL_URL = "https://www.airbnb.com/oauth2/auth?{query}"

    def verify_access(self, access_params) -> dict:
        url = self.VERIFY_URL
        try:
            access_data = self._call_api(
                "post",
                url,
                json={"code": access_params["code"]},
                auth=(self._client_id, self._client_secret),
            )
        except requests.HTTPError as e:
            content = getattr(e.response, "content", None)
            logger.info("Could not get data from Airbnb oauth.access: %s", content)
            access_data = {}
        except requests.Timeout:
            logger.info("Connection to %s timed out", url)
            access_data = {}
        return access_data

    def refresh_token(self, refresh_token):
        response = requests.post(
            self.VERIFY_URL,
            json={"refresh_token": refresh_token},
            auth=(self._client_id, self._client_secret),
            timeout=5,
        )
        response.raise_for_status()
        return response.json()

    def revoke_token(self, access_token):
        response = requests.delete(
            f"https://api.airbnb.com/v2/oauth2/authorizations/{access_token}?_unwrapped=true",
            auth=(self._client_id, self._client_secret),
            timeout=5,
        )

        # Token can be already revoked which causes 404
        if response.status_code == HTTP_404_NOT_FOUND:
            return {}
        else:
            response.raise_for_status()
            return response.json()

    def check_token(self, access_token: str) -> bool:
        response = requests.get(
            f"https://api.airbnb.com/v2/oauth2/authorizations/{access_token}?_unwrapped=true",
            auth=(self._client_id, self._client_secret),
        )
        return response.ok and response.json().get("valid", False)

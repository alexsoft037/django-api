import logging

from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_extensions.mixins import NestedViewSetMixin

from listings.serializers import PropertyCreateSerializer
from rental_integrations.exceptions import ServiceException
from rental_integrations.service import HTTP_499_NOT_MY_FAULT
from rental_integrations.views import BaseAccountViewSet
from . import serializers as sers
from .models import HomeAwayAccount
from .service import HomeAwayService

logger = logging.getLogger(__name__)


def _update_listings(account: HomeAwayAccount) -> (int, dict):
    ok = account.update_listings(commit=True)
    if ok:
        resp_status = status.HTTP_201_CREATED
        resp_data = sers.HomeAwayAccountSerializer(account).data
    else:
        resp_status = HTTP_499_NOT_MY_FAULT
        resp_data = {"error": "Problem making request to Homeaway"}
    return resp_status, resp_data


class HomeAwayAccountViewSet(BaseAccountViewSet, viewsets.ModelViewSet):
    """Views for intergration with Homeaway service.

    retrieve:
    Return a given Homeaway account details, including listings data.

    list:
    Return a list of all the integrated Homeaway accounts.

    create:
    Create a new Homeaway integration.

    There might be many integrations for each user account. User is automatically
    logged in to Homeaway but sometimes 2FA might be needed.

    destroy:
    Delete a given Homeaway integration.
    """

    serializer_class = sers.HomeAwayAccountSerializer
    queryset = HomeAwayAccount.objects.all()

    def _login(self, username, password):
        service = HomeAwayService(username=username, password=password)
        resp = service.authenticate(username, password)
        data = {}
        if resp["success"]:
            data = resp["data"]
        status_code = resp["status"]
        if status_code == status.HTTP_412_PRECONDITION_FAILED:
            status_code = status.HTTP_202_ACCEPTED
        return status_code, data, service.get_session_info()

    def get_response(self):
        if hasattr(self, "_resp_data") and hasattr(self, "_status"):
            return Response(data=self._resp_data, status=self._status)
        else:
            return None

    def perform_create(self, serializer):
        """
        username = serializer.validated_data["username"]
        password = serializer.validated_data["password"]
        status_code, data, session = self._login(username, password)

        if status_code == status.HTTP_200_OK:
            account = serializer.save(
                organization=self.request.user.organization, data=data, session=session
            )
            self._status, self._resp_data = _update_listings(account)
        elif status_code == status.HTTP_202_ACCEPTED:
            account = serializer.save(
                organization=self.request.user.organization, data=data, session=session
            )
            phones = []
            if "phoneNumbers" in data:
                phones = [
                    {
                        "id": phone_number.get("phoneNumberId"),
                        "obfuscated_number": phone_number.get("maskedNumber"),
                    }
                    for phone_number in data["phoneNumbers"]
                ]
            self._resp_data = self.get_serializer(account).data
            self._resp_data.update({"methods": ["text"], "phones": phones})
            self._status = status_code
        else:
            self._resp_data = {"error": "Error occured"}
            self._status = HTTP_499_NOT_MY_FAULT
        """
        # For demo purposes
        self._resp_data = {}
        self._status = status.HTTP_202_ACCEPTED

    @action(detail=True, methods=["POST"])
    def login(self, request, pk):
        """Log in into previously created Homeaway account."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = get_object_or_404(HomeAwayAccount, pk=pk, organization=request.user.organization)

        resp_status, data, session = self._login(
            account.user_id, serializer.validated_data["password"]
        )
        if resp_status in (status.HTTP_201_CREATED, status.HTTP_202_ACCEPTED):
            account.data = data
            account.session = session
            account.save()
        return Response(status=resp_status, data=data)

    @action(
        detail=True, methods=["POST"], url_path="import", serializer_class=sers.ImportSerializer
    )
    def import_listings(self, request, pk):
        """
        Import listings with given Homeaway IDs.

        Returns list of successfully imported listings and list of listings
        that were unable to parse:

            {
                "success": [1, 2, 4],
                "error": [3, 5],
            }
        """
        account = get_object_or_404(HomeAwayAccount, pk=pk, organization=request.user.organization)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resp_status = status.HTTP_200_OK
        success = []
        errors = []
        pks = serializer.validated_data["listings"]
        for prop in account.listing_set.filter(pk__in=pks):
            s = PropertyCreateSerializer(data=prop.data, context={"request": request})
            if s.is_valid():
                s.save(organization=request.user.organization)
                success.append(prop.pk)
            else:
                errors.append(prop.pk)
                logger.warn(
                    "Invalid Homeaway listing! Account: %d, listings: %d, errors: %s",
                    account.pk,
                    prop.pk,
                    s.errors,
                )

        if success:
            resp_status = status.HTTP_201_CREATED

        return Response(status=resp_status, data={"success": success, "error": errors})

    @action(detail=True, methods=["POST"])
    def fetch(self, request, pk):
        account = get_object_or_404(HomeAwayAccount, pk=pk, organization=request.user.organization)
        resp_status, resp_data = _update_listings(account)
        return Response(data=resp_data, status=resp_status)


class Homeaway2faViewSet(NestedViewSetMixin, viewsets.GenericViewSet):
    """Verify Homeaway login with 2 factor authentication."""

    serializer_class = sers.Homeaway2faSerializer

    def create(self, request, *, pk=None):
        """
        Send a verification code using preferred method (like phone, text, email).

        Returns:
          * `201` if a verification code was sent,
          * `202` if you more information needs to be provided,
          * `400` if there is an invalid response from Homeaway.
        """
        account = get_object_or_404(HomeAwayAccount, pk=pk, organization=request.user.organization)

        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        phone_id = serializer.data.get("phone_id", "")
        method = serializer.data["method"]

        data = account.data or {}

        if phone_id:
            data["phone_id"] = phone_id
        account.data = data
        account.save()

        if method == "text" and not phone_id:
            resp_status = status.HTTP_202_ACCEPTED
            return Response(data={"error": "Choose phone_id"}, status=resp_status)

        homeaway_resp = account.service.submit_challenge_request(data)
        resp_json = homeaway_resp.json()
        account.data.update(resp_json)
        account.save()

        if homeaway_resp.ok:
            if resp_json["status"] == "SUCCESS":
                resp_status = homeaway_resp.status_code
                resp_data = {"success": "2FA code sent"}
            else:
                resp_status = status.HTTP_400_BAD_REQUEST
                try:
                    msg = resp_json["status"]
                    attempts = resp_json["numberAttemptsRemaining"]
                except KeyError:
                    msg = ("Unkown error",)
                    attempts = (0,)
                resp_data = {"error": msg, "numberAttemptsRemaining": attempts}

            return Response(data=resp_data, status=resp_status)
        raise ServiceException(data, **data)

    @action(detail=False, methods=["POST"], serializer_class=sers.HomeawayCodeSerializer)
    def confirm(self, request, pk=None):
        """
        Attempt to confirm log in with a provided single-use verification code.

        Returns:
          * `201` and listings stubs if code is valid,
          * `202` if code is invalid,
          * `400` if can't create valid request or got invalid response from Homeaway.

        """
        account = get_object_or_404(HomeAwayAccount, pk=pk, organization=request.user.organization)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = account.data or {}
        data.update(serializer.validated_data)

        try:
            homeaway_resp = account.service.submit_challenge_verification(data)
            logger.info(homeaway_resp.json())
        except KeyError as e:
            logger.warning("Error while confirming Homeaway 2FA code: %s", e)
            resp_status = status.HTTP_400_BAD_REQUEST
            resp_data = {"error": "Unknown error"}
        else:
            resp_json = homeaway_resp.json()
            if resp_json["status"] == "SUCCESS":
                account_details = resp_json.get("accountDetails")
                account.service._user_id = account_details["userID"]
                account.service._access_token = homeaway_resp.cookies["HA_SESSION"]
                if callable(account.service._auth_callback):
                    account.service._auth_callback(service=account.service)
                resp_status, resp_data = _update_listings(account)
            elif resp_json["status"] == "INVALID_CODE":
                resp_status = status.HTTP_400_BAD_REQUEST
                resp_data = {"error": "Invalid or expired 2FA code"}
            elif resp_json["status"] == "LOCKED_OUT":
                resp_status = status.HTTP_400_BAD_REQUEST
                resp_data = {"error": "The account has been blocked"}
            else:
                resp_status = status.HTTP_400_BAD_REQUEST
                resp_data = {"error": "Invalid or expired 2FA code"}

        return Response(data=resp_data, status=resp_status)

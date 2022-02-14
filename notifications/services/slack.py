import logging

import requests
from django.conf import settings

from listings.choices import ReservationStatuses
from notifications.services.sms import ServiceError

logger = logging.getLogger(__name__)

RED = "#ff0000"
GREEN = "#36a64f"
BLUE = "#1d9bd1"
CANCELLATION = "A reservation was cancelled @ <{base_url}/properties/{prop_id}|{full_address}>"
UPDATE = "A reservation was updated @ <{base_url}/properties/{prop_id}|{full_address}>"
CREATE = "A reservation was created @ <{base_url}/properties/{prop_id}|{full_address}>"
CHECK_IN = "Check-in"
CHECK_OUT = "Check-out"
GUEST = "Guest"
STATUS = "Status"
UPDATED_FIELDS = "Updated Fields"
UPDATED_FIELD_TEXT = "`{name}` - `{old_value}` -> `{new_value}`\n"
RESERVATION_TITLE_LINK = "{url}reservations/{reservation_id}"

CANCELLATION_TITLE = "Reservation Cancelled: {confirmation_code}"
UPDATED_TITLE = "Reservation Updated: {confirmation_code}"
CREATED_TITLE = "Reservation Created: {confirmation_code}"

FOOTER_TITLE = "Cozmo Notifications"
FOOTER_ICON = ""


class SlackService:
    @staticmethod
    def send_webhook_message(url, **kwargs):
        data = {"attachments": [kwargs]}
        response = requests.post(url, json=data)
        if response.ok:
            pass
        else:
            logger.warning("Unable to send message - Got non-200 status_code")
        raise ServiceError()


class SlackMessageBuilder:
    def _get_field(self, title, value, short=False):
        return {"title": title, "value": f"`{value}`", "short": short}

    def _get_message(self, **kwargs):
        return {
            "attachments": [
                {
                    "markdwn_in": ["fields"],
                    "footer": FOOTER_TITLE,
                    "footer_icon": FOOTER_ICON,
                    **kwargs,
                }
            ]
        }

    def _get_negative_message(self, **kwargs):
        return self._get_message(**kwargs, color=RED)

    def _get_positive_message(self, **kwargs):
        return self._get_message(**kwargs, color=GREEN)

    def _get_neutral_message(self, **kwargs):
        return self._get_message(**kwargs, color=BLUE)

    def _get_default_fields(self, reservation):
        return [
            self._get_field(CHECK_IN, reservation.start_date, True),
            self._get_field(CHECK_OUT, reservation.end_date, True),
            self._get_field(GUEST, reservation.guest.full_name, True),
            self._get_field(STATUS, ReservationStatuses(reservation.status).name, True),
        ]

    def get_reservation_cancellation_message(self, reservation):
        text = CANCELLATION.format(
            base_url=settings.COZMO_WEB_URL,
            prop_id=reservation.prop.pk,
            full_address=reservation.prop.full_address,
        )
        return self._get_negative_message(
            fallback=text,
            title=CANCELLATION_TITLE.format(confirmation_code=reservation.confirmation_code),
            title_link=RESERVATION_TITLE_LINK.format(
                url=settings.COZMO_WEB_URL, reservation_id=reservation.pk
            ),
            text=text,
            fields=self._get_default_fields(reservation),
        )

    def get_reservation_update_message(self, reservation):
        fields = "".join(
            [
                UPDATED_FIELD_TEXT.format(
                    name=key, old_value=value, new_value=getattr(reservation, key)
                )
                for key, value in reservation._changed_fields().items()
            ]
        )
        text = UPDATE.format(
            base_url=settings.COZMO_WEB_URL,
            prop_id=reservation.prop.pk,
            full_address=reservation.prop.full_address,
        )
        message = self._get_neutral_message(
            fallback=text,
            title=UPDATED_TITLE.format(confirmation_code=reservation.confirmation_code),
            title_link=RESERVATION_TITLE_LINK.format(
                url=settings.COZMO_WEB_URL, reservation_id=reservation.pk
            ),
            text=text,
            fields=[
                *self._get_default_fields(reservation),
                {"title": UPDATED_FIELDS, "value": fields, "short": False},
            ],
        )
        return message

    def get_reservation_created_message(self, reservation):
        text = CREATE.format(
            base_url=settings.COZMO_WEB_URL,
            prop_id=reservation.prop.pk,
            full_address=reservation.prop.full_address,
        )
        message = self._get_positive_message(
            fallback=text,
            title=CREATED_TITLE.format(confirmation_code=reservation.confirmation_code),
            title_link=RESERVATION_TITLE_LINK.format(
                url=settings.COZMO_WEB_URL, reservation_id=reservation.pk
            ),
            text=text,
            fields=self._get_default_fields(reservation),
        )
        return message

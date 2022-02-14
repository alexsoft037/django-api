from contextlib import suppress
from datetime import date, datetime

from listings.choices import (
    FeeTypes,
    ReservationStatuses,
    SecurityDepositTypes as ListingSecurityDepositTypes,
    TaxTypes,
)
from listings.models import Reservation
from rental_integrations.airbnb import choices, mappings
from rental_integrations.airbnb.mappings import airbnb_fees, airbnb_reservation_status_to_cozmo


def _to_cozmo_guest(reservation: dict) -> dict:
    data = dict(
        first_name=reservation.get("guest_first_name"),
        last_name=reservation.get("guest_last_name"),
        email=reservation.get("guest_email"),
        external_id=reservation.get("guest_id"),
        locale=reservation.get("guest_preferred_locale"),
    )
    phone_numbers = reservation.get("guest_phone_numbers")

    with suppress(IndexError):
        data["phone"] = phone_numbers[0].replace("-", "")
        data["secondary_phone"] = phone_numbers[1].replace("-", "")

    return data


def _get_date(d):
    if not isinstance(d, date):
        return datetime.strptime(d, "%Y-%m-%d")
    return d


def _to_cozmo_rate(reservation: dict) -> dict:
    #  Duration automatically set by reservation
    start_date = _get_date(reservation.get("start_date"))
    end_date = _get_date(reservation.get("end_date"))
    duration = (end_date - start_date).days
    if reservation.get("status") == ReservationStatuses.Cancelled.value:
        rate = dict(value=reservation.get("listing_cancellation_payout"), duration=duration)
    else:
        rate = dict(
            value=(
                reservation.get("listing_base_price_accurate")
                or reservation.get("listing_base_price")
            ),
            duration=duration,
        )
    return rate


def _to_cozmo_fees(reservation: dict) -> dict:
    data = list()
    data.append(
        dict(
            type=FeeTypes.Platform_Fee.pretty_name,
            name="Airbnb Host Fee",
            value=float(reservation.get("listing_host_fee_accurate")) * -1,
            custom=True,
        )
    )
    if reservation.get("listing_security_price_accurate"):
        data.append(
            dict(
                type=ListingSecurityDepositTypes.Security_Deposit.pretty_name,
                name="Security Deposit",
                value=reservation.get("listing_security_price_accurate"),
                refundable=True,
                custom=True,
            )
        )
    if reservation.get("listing_cleaning_fee_accurate"):
        data.append(
            dict(
                type=FeeTypes.Service_Fee.pretty_name,
                name="Cleaning Fee",
                value=reservation.get("listing_cleaning_fee_accurate"),
                custom=True,
            )
        )
    if reservation.get("standard_fees_details"):
        for fee in reservation.get("standard_fees_details"):
            data.append(
                dict(
                    name=airbnb_fees[fee["fee_type"]],
                    value=fee["amount_native"],
                    type=airbnb_fees[fee["fee_type"]],
                )
            )

    if reservation.get("transient_tax_details"):
        for tax in reservation.get("transient_tax_details"):
            data.append(
                dict(
                    name=tax["name"],
                    value=float(tax["amount_usd"]),
                    type=TaxTypes.Local_Tax.pretty_name,
                    custom=True,
                )
            )
    return data


def to_cozmo_reservation(reservation: dict) -> dict:
    guest_details = reservation.get("guest_details")
    data = dict(
        guest=_to_cozmo_guest(reservation),
        start_date=reservation.get("start_date"),
        end_date=reservation.get("end_date"),
        confirmation_code=reservation.get("confirmation_code"),
        price=float(reservation.get("expected_payout_amount_accurate")),
        paid=float(reservation.get("expected_payout_amount_accurate")),
        guests_adults=guest_details.get("number_of_adults"),
        guests_children=guest_details.get("number_of_children"),
        guests_infants=guest_details.get("number_of_infants"),
        date_booked=reservation.get("booked_at"),
        status=airbnb_reservation_status_to_cozmo.get(
            choices.ReservationStatus[reservation.get("status_type")]
        ).pretty_name,
        source=Reservation.Sources.Airbnb.name,
        cancellation_policy=mappings.airbnb_cancellation_policy.get(
            reservation.get("cancellation_policy_category")
        ),
        send_email=False,
        fees=_to_cozmo_fees(reservation),
        rate=_to_cozmo_rate(reservation),
        external_id=reservation.get("confirmation_code"),
    )
    return data

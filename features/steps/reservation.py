from behave import then, when
from rest_framework import status
from rest_framework.test import APIClient

from listings.models import Rate

client = APIClient()


@when("user creates a new reservation")
def new_reservation(context):
    start_date = "2017-07-31"
    Rate.objects.create(nightly=1, time_frame=(start_date, None), prop_id=context.prop_id)

    client.credentials(HTTP_AUTHORIZATION="JWT " + context.token)
    resp = client.post(
        "/reservations/",
        data={
            "guest": {
                "first_name": "Ulrich",
                "email": "urlich@example.org",
                "avatar": "http://example.org/avtar/",
            },
            "start_date": start_date,
            "end_date": "2017-08-31",
            "paid": 10,
            "guests_adults": 2,
            "guests_children": 1,
            "guests_infants": 0,
            "prop": context.prop_id,
        },
    )

    assert resp.status_code == status.HTTP_201_CREATED
    resp = resp.json()
    assert isinstance(resp.get("guest"), dict)
    context.reservation_id = resp["id"]


@then("user can see a new reservation listed")
def list_reservations(context):
    resp = client.get("/reservations/")
    new_res = [r for r in resp.json()["results"] if r["id"] == context.reservation_id]
    assert len(new_res) == 1
    guest = new_res[0]["guest"]
    assert isinstance(guest, dict)

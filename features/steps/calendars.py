from unittest import mock

from behave import given, then, when
from icalendar import Calendar
from rest_framework import status
from rest_framework.test import APIClient

from listings.calendars.models import CozmoCalendar

client = APIClient()


@when("user sees a calendar preview")
def cal_preview(context):
    client.credentials(HTTP_AUTHORIZATION="JWT " + context.token)
    cal_id = CozmoCalendar.objects.get(prop_id=context.prop_id).pk
    with mock.patch(
        "listings.calendars.serializers.models.CheckCalendar.fetch", return_value=True
    ):
        resp = client.post("/calendars/check_url/", {"url": "https://example.org/ical"})
    assert resp.status_code == status.HTTP_200_OK
    resp_data = resp.json()
    assert "events_count" in resp_data
    context.cal_id = cal_id


@when("user imports a calendar")
def import_cal(context):
    client.credentials(HTTP_AUTHORIZATION="JWT " + context.token)
    with mock.patch(
        "listings.calendars.serializers.models.ExternalCalendar.fetch", return_value=True
    ):
        resp = client.post(
            "/calendars/{}/external/".format(context.cal_id),
            {
                "url": "https://example.org/ical",
                "name": "Some name",
                "description": "Some description",
            },
        )
    assert resp.status_code == status.HTTP_201_CREATED
    resp_data = resp.json()
    assert "events_count" in resp_data
    context.ext_cal_id = resp_data["id"]


@then("user sees imported calendar details")
def cal_imported(context):
    resp = client.get("/calendars/{}/external/{}/".format(context.cal_id, context.ext_cal_id))
    assert resp.status_code == status.HTTP_200_OK

    resp = client.get("/calendars/{}/".format(context.cal_id, context.ext_cal_id))
    resp_data = resp.json()
    assert resp.status_code == status.HTTP_200_OK
    external_cals = resp_data.get("external_cals", None)
    assert external_cals
    new_cal = [ec for ec in external_cals if ec["id"] == context.ext_cal_id]
    assert len(new_cal) == 1


@given("Cozmo calendar exists")
def cozmo_cal_exists(context):
    context.cal_id = CozmoCalendar.objects.get(prop_id=context.prop_id).pk
    del context.prop_id


@when("anonymous user visits calendar page")
def visit_ical(context):
    resp = client.get("/calendars/{}/ical/".format(context.cal_id))
    assert resp.status_code == status.HTTP_200_OK
    assert "text/calendar" in resp["Content-Type"]
    context.ical = resp.content


@then("anonymous user recieves iCal file")
def exported_ical(context):
    try:
        Calendar.from_ical(context.ical)
    except Exception:
        raise ValueError("Returned data is not a valid iCal")

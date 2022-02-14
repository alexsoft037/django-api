from behave import given, then, when
from rest_framework import status
from rest_framework.test import APIClient

from accounts.profile.choices import Plan

client = APIClient()


@when("user submits onboarding data")
def submit_onboarding(context):
    client.credentials(HTTP_AUTHORIZATION="JWT " + context.token)
    data = {"team": 1, "properties": 2, "plan": Plan.SINGLE.value}
    context.status_code = client.post("/auth/organization/plan/", data).status_code


@then("plan is sucessfully selected")
def plan_selected(context):
    print(context.status_code)
    assert context.status_code == status.HTTP_201_CREATED
    del context.status_code


@given("user already had onboarding")
def had_onboarding(context):
    client.credentials(HTTP_AUTHORIZATION="JWT " + context.token)
    data = {"team": 5, "properties": 1, "plan": Plan.SINGLE.value}
    client.post("/auth/organization/plan/", data)


@then("plan is not updated")
def plan_not_updated(context):
    assert context.status_code == status.HTTP_400_BAD_REQUEST
    del context.status_code

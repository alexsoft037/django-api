from behave import given, when
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from accounts.choices import ApplicationTypes

client = APIClient()
DjangoUserModel = get_user_model()


def create_account(mail, password):
    data = {
        "email": mail,
        "password": password,
        "first_name": "Egg",
        "last_name": "Spam",
        "phone": "+1999999999",
    }
    client.post("/auth/registration/", data)
    print('11111111111111')
    email = DjangoUserModel.objects.get(username=mail).emailaddress_set.first()
    confirm = email.send_confirmation().key
    client.post("/auth/registration/verify-email/", {"key": confirm})


@given("account with given email exists")
def account_with_email_exists(context):
    context.username = "mail@example.org"
    context.password = "1Some-password"
    create_account(context.username, context.password)
    user_qs = DjangoUserModel.objects.filter(email=context.username)
    assert user_qs.count() == 1
    context.user = user_qs.first()
    assert context.user.check_password(context.password)


@given("account has right permissions")
def account_has_right_permissions(context):
    organization = context.user.organization
    organization.applications = (*organization.applications, ApplicationTypes.Reservation.value)
    organization.save()


def log_in(context):
    data = {"username": context.username, "password": context.password}
    resp = client.post("/auth/login/", data)
    assert resp.status_code == status.HTTP_200_OK
    del context.username
    del context.password
    context.token = resp.data["token"]


is_loged_in = given("user is logged in")(log_in)

logs_in = when("user logs in")(log_in)

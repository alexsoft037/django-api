from behave import given, then, when
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient


client = APIClient()
DjangoUserModel = get_user_model()


@given("user registers with necessary data")
def step_signs_up(context):
    context.username = "mail@example.org"
    context.password = "Unique-password123"
    data = {
        "email": context.username,
        "password": context.password,
        "first_name": "Egg",
        "last_name": "Spam",
        "phone": "+1999999999",
    }
    resp = client.post("/auth/registration/", data)
    print('222222222222222222222')
    assert resp.status_code == status.HTTP_201_CREATED
    assert "detail" in resp.data

    user = DjangoUserModel.objects.get(username=context.username)
    assert user.first_name == "Egg"
    assert user.last_name == "Spam"
    assert user.phone == "+1999999999"
    assert user.check_password(context.password)
    assert user.emailaddress_set.count() == 1
    email_obj = user.emailaddress_set.first()
    assert email_obj.email == context.username
    context.email = email_obj


@given("server sends confirmation email")
def send_confirmation(context):
    assert context.email.emailconfirmation_set.count() == 0  # HMAC does not store objects in DB
    assert context.email.verified is False
    confirm = context.email.send_confirmation()
    context.confirmation = confirm.key


@when("user clicks a verification url")
def click_ver_email(context):
    resp = client.post("/auth/registration/verify-email/", {"key": context.confirmation})
    assert resp.status_code == status.HTTP_200_OK
    del context.confirmation
    del context.email


@then("user finishes registration")
def finish_registration(context):
    client.credentials(HTTP_AUTHORIZATION="JWT " + context.token)
    resp = client.patch(
        "/auth/user/",
        {
            "account_type": DjangoUserModel.AllowedTypes.Small_Owner.pretty_name,
            "first_name": "Egg",
            "last_name": "Spam",
        },
    )
    assert resp.status_code == status.HTTP_200_OK


@given("admin user exists")
def admin_exists(context):
    context.admin_username = "admin"
    context.admin_password = "password"
    DjangoUserModel.objects.create_superuser(
        username=context.admin_username, password=context.admin_password, email="admin@example.org"
    )


@when("admin logs in")
def admin_logs_in(context):
    assert client.login(username=context.admin_username, password=context.admin_password)
    del context.admin_username
    del context.admin_password


@then("admin can manage website")
def admin_access_panel(context):
    resp = client.get("/admin/")
    client.logout()

    assert resp.status_code == status.HTTP_200_OK

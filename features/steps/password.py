import re

from behave import given, then, when
from django.contrib.auth import get_user_model
from django.core import mail
from rest_framework import status
from rest_framework.test import APIClient

client = APIClient()
DjangoUserModel = get_user_model()


@given("account with given email does not exist")
def no_such_email(context):
    context.username = "invalid@example.org"
    assert DjangoUserModel.objects.filter(email=context.username).count() == 0


@given("user requests password reset")
def password_reset(context):
    mail.outbox = []
    data = {"email": context.username}
    resp = client.post("/auth/password/reset/", data)
    assert resp.status_code == status.HTTP_200_OK


@when("user clicks the password reset link")
def reset_link_clicked(context):
    assert len(mail.outbox) == 1
    result = re.search(r"reset-password\?uid=([\w\d\-_]+)&token=([\w\d-]+)", mail.outbox[0].body)
    assert len(result.groups()) == 2
    context.uid, context.token = result.groups()
    mail.outbox = []


@when("user provides a new password")
def set_new_password(context):

    context.new_password = "1New-pass"
    data = {
        "uid": context.uid,
        "token": context.token,
        "new_password1": context.new_password,
        "new_password2": context.new_password,
    }
    del context.uid
    del context.token

    user = DjangoUserModel.objects.get(email=context.username)
    assert user.check_password(context.new_password) is False

    resp = client.post("/auth/password/reset/confirm/", data)
    assert resp.status_code == status.HTTP_200_OK


@then("the new password is set")
def check_new_password(context):
    user = DjangoUserModel.objects.get(email=context.username)
    assert user.check_password(context.new_password)


@then("the email is not sent")
def email_not_sent(context):
    assert len(mail.outbox) == 0

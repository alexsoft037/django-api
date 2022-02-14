from urllib.parse import urljoin

from django.conf import settings
from django.db import models
from django.urls import reverse

from accounts.models import Organization
from cozmo.storages import UploadImageTo
from rental_integrations.airbnb.models import AirbnbAccount
from rental_integrations.booking.models import BookingAccount
from rental_integrations.homeaway.models import HomeAwayAccount
from rental_integrations.trip_advisor.models import TripAdvisorAccount


def backend_apps(*, key, view_name):
    def inner(klass):
        assert not isinstance(key, bool)
        assert isinstance(key, int)
        assert key not in backend_apps.registry
        backend_apps.registry[key] = klass
        backend_apps.view_names[key] = view_name
        return klass

    return inner


backend_apps.registry = {}
backend_apps.view_names = {}


class Tag(models.Model):

    name = models.CharField(max_length=25)

    def __str__(self):
        return self.name


@backend_apps(key=1, view_name="appmarket:google-list")
class GoogleApp(models.Model):

    user_id = models.CharField(max_length=150)
    credentials = models.TextField()
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)


@backend_apps(key=0, view_name="appmarket:slack-list")
class SlackApp(models.Model):

    access_token = models.TextField()
    team_name = models.CharField(max_length=150)
    team_id = models.CharField(max_length=150)
    url = models.URLField()
    channel = models.CharField(max_length=150)
    configuration_url = models.URLField()
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)


@backend_apps(key=2, view_name="appmarket:stripe-list")
class StripeApp(models.Model):

    access_token = models.TextField()
    refresh_token = models.TextField()
    stripe_publishable_key = models.TextField()
    stripe_user_id = models.CharField(max_length=150)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)


@backend_apps(key=3, view_name="appmarket:mailchimp-list")
class MailChimpApp(models.Model):

    access_token = models.TextField()
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)


class AirbnbApp(models.Model):
    access_token = models.TextField()
    refresh_token = models.TextField()
    user_id = models.TextField()
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)


backend_apps(key=5, view_name="booking:booking-integration-list")(BookingAccount)
backend_apps(key=6, view_name="homeaway:homeaway-list")(HomeAwayAccount)
backend_apps(key=7, view_name="tripadvisor:tripadvisor-list")(TripAdvisorAccount)
backend_apps(key=4, view_name="appmarket:airbnb-list")(AirbnbAccount)


class App(models.Model):

    name = models.CharField(max_length=50)
    image = models.ImageField(
        upload_to=UploadImageTo("app_marketplace"), help_text="Preferably a logo"
    )
    description = models.TextField()
    backend_app = models.SmallIntegerField(choices=tuple(backend_apps.registry.items()), null=True)
    tags = models.ManyToManyField(Tag)

    def __str__(self):
        return self.name

    @property
    def backend_model(self):
        return backend_apps.registry[self.backend_app]

    @property
    def install_url(self):
        return urljoin(settings.COZMO_WEB_URL, reverse(backend_apps.view_names[self.backend_app]))

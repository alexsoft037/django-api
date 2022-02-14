from .settings_base import *  # noqa: F403

ENV_TYPE = "dev"

INSTALLED_APPS += ["internal.apps.InternalConfig"]  # noqa: F405

ALLOWED_HOSTS = [
    "cozmo-api-dev.voyajoy.com",
    "api-staging-cozmo.voyajoy.com",  # XXX Remove after DNS change
    "127.0.0.1",
]

COZMO_WEB_URL = f"https://cozmo-{ENV_TYPE}.voyajoy.com/"
COZMO_CALENDAR_URL = f"https://api-cozmo-{ENV_TYPE}.voyajoy.com/calendars/{{id}}/ical/"

NEXMO.update({"TO": "14152995346"})  # noqa: F405

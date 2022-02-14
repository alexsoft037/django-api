from .settings_base import *  # noqa: F403

ENV_TYPE = "sandbox"

INSTALLED_APPS += ["internal.apps.InternalConfig"]  # noqa: F405

ALLOWED_HOSTS = [
    "cozmo-api-sandbox.voyajoy.com",
    "sandbox-api-cozmo.voyajoy.com",  # XXX Remove after DNS change
]

COZMO_CALENDAR_URL = f"https://api-cozmo-{ENV_TYPE}.voyajoy.com/calendars/{{id}}/ical/"

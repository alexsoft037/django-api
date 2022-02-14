from .settings_base import *  # noqa: F403

ENV_TYPE = "staging"

INSTALLED_APPS += ["internal.apps.InternalConfig"]  # noqa: F405

ALLOWED_HOSTS = ["cozmo-api-staging.voyajoy.com"]

COZMO_WEB_URL = f"https://cozmo-{ENV_TYPE}.voyajoy.com/"
COZMO_CALENDAR_URL = f"https://api-cozmo-{ENV_TYPE}.voyajoy.com/calendars/{{id}}/ical/"

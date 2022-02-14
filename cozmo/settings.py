from .settings_base import *  # noqa: F403

ENV_TYPE = "dev"

INSTALLED_APPS += ["internal.apps.InternalConfig", "corsheaders", ]  # noqa: F405

ALLOWED_HOSTS = [
    "cozmo-api-dev.voyajoy.com",
    'liuxiaobai.xyz',
    "api-staging-cozmo.voyajoy.com",  # XXX Remove after DNS change
]


MIDDLEWARE.insert(  # noqa: F405
    MIDDLEWARE.index("django.middleware.common.CommonMiddleware"),  # noqa: F405
    "corsheaders.middleware.CorsMiddleware",
)

CORS_ALLOW_CREDENTIALS = True
CORS_ORIGIN_ALLOW_ALL = True

CORS_ALLOW_METHODS = (
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
    'VIEW',
)

CORS_ALLOW_HEADERS = (
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with'
)

COZMO_WEB_URL = f"https://cozmo-{ENV_TYPE}.voyajoy.com/"
COZMO_CALENDAR_URL = f"https://api-cozmo-{ENV_TYPE}.voyajoy.com/calendars/{{id}}/ical/"

NEXMO.update({"TO": "14152995346"})  # noqa: F405

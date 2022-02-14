from .settings_base import *  # noqa: F403

ENV_TYPE = "test"



INSTALLED_APPS += ["behave_django", "corsheaders", "internal.apps.InternalConfig"]  # noqa: F405

ALLOWED_HOSTS = ["*"]

COZMO_WEB_URL = "http://127.0.0.1:3000/"
COZMO_CALENDAR_URL = "http://127.0.0.1/calendars/{id}/ical/"

MIDDLEWARE.insert(  # noqa: F405
    MIDDLEWARE.index("django.middleware.common.CommonMiddleware"),  # noqa: F405
    "corsheaders.middleware.CorsMiddleware",
)

DEFAULT_FILE_STORAGE = "cozmo.storages.DummyCDNStorage"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

AZURE_EMULATED_MODE = True

CORS_ORIGIN_ALLOW_ALL = True
CORS_ORIGIN_WHITELIST = ()

REST_FRAMEWORK.update({"DEFAULT_THROTTLE_RATES": {"burst": None, "sustained": None}})

TWILIO = {  # Twilio test credentials
    "ACCOUNT": "AC4353822aa6509f94c86a7019f93aef39",
    "TOKEN": "238d28f32f01f676f9747ca8aab539e2",
    "FROM": "+15005550006",
}

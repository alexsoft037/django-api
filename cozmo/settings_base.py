"""
Django settings for cozmo project.

Generated by 'django-admin startproject' using Django 1.11.1.

For more information on this file, see
https://docs.djangoproject.com/en/1.11/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.11/ref/settings/
"""
import environ

import os
import ssl
import sys
from datetime import timedelta

from django.core.exceptions import ImproperlyConfigured
# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))


def _required_env(name):
    try:
        value = os.environ[name]
        if not value:
            raise KeyError
        return value
    except KeyError:
        raise ImproperlyConfigured('Missing env variable: "{}"'.format(name)) from None


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.11/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = _required_env("DJ_SECRET")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DJ_DEBUG") == "True"

ALLOWED_HOSTS = ['*']
COZMO_CALENDAR_URL = ""

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.messages",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.postgres",
    "guardian",
    "storages",
    "rest_framework",
    "rest_framework_swagger",
    "rest_framework_tracking",
    #  'rest_framework.authtoken',
    "rest_framework_jwt",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "rest_auth",
    "rest_auth.registration",
    # cozmo apps
    "cozmo_common.apps.CozmoCommonConfig",
    "accounts.apps.AccountsConfig",
    "automation.apps.AutomationConfig",
    "accounts.profile.apps.ProfileConfig",
    "app_marketplace.apps.AppMarketplaceConfig",
    "crm.apps.CrmConfig",
    "listings.apps.ListingsConfig",
    "events.apps.EventsConfig",
    "listings.calendars.apps.CalendarsConfig",
    "notifications.apps.NotificationsConfig",
    "owners.apps.OwnersConfig",
    "pois.apps.PoisConfig",
    "payments.apps.PaymentsConfig",
    "public_api.apps.PublicApiConfig",
    "message_templates.apps.MessageTemplatesConfig",
    "rental_connections.apps.RentalConnectionsConfig",
    "rental_integrations.apps.RentalIntegrationsConfig",
    "rental_integrations.airbnb.apps.AirbnbConfig",
    "rental_integrations.booking.apps.BookingConfig",
    "rental_integrations.expedia.apps.ExpediaConfig",
    "rental_integrations.homeaway.apps.HomeawayConfig",
    "rental_integrations.trip_advisor.apps.TripAdvisorConfig",
    "send_mail.apps.SendMailConfig",
    "search.apps.SearchConfig",
    "vendors.apps.VendorsConfig",
    "send_mail.phone.apps.PhoneConfig",
    "services.apps.ServicesConfig",
    "chat.apps.ChatConfig",
    "settings.apps.SettingsConfig",
    "rental_network.apps.RentalNetworkConfig",
    "dashboard.apps.DashboardConfig",
    "pricing.apps.PricingConfig",
]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[cozmo] %(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s"  # noqa E501
        },
        "celery": {
            "format": "[celery] %(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s"
        },
    },
    "filters": {"require_debug_false": {"()": "django.utils.log.RequireDebugFalse"}},
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "stream": sys.stdout,
        },
        "celery": {"class": "logging.StreamHandler", "formatter": "celery"},
        "django": {"class": "logging.StreamHandler", "formatter": "verbose", "stream": sys.stderr},
    },
    "loggers": {
        "cozmo": {"handlers": ["console"], "level": "ERROR"},
        "webhook": {"handlers": [], "level": "INFO", "propagate": True},
        "celery": {"handlers": ["celery"], "level": "ERROR", "propagate": False},
        "django": {"handlers": ["django"], "level": "ERROR", "propagate": False},
        # "django.request": {"handlers": [], "level": "ERROR", "propagate": True},
    },
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "cozmo.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]


WSGI_APPLICATION = "cozmo.wsgi.application"

# Database
# https://docs.djangoproject.com/en/1.11/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _required_env("PG_DB"),
        "USER": _required_env("PG_USER"),
        "PASSWORD": _required_env("PG_PASS"),
        "HOST": "ec2-34-224-226-38.compute-1.amazonaws.com",
        "PORT": "5432",
        "CONN_MAX_AGE": None,
    }
}

# Password validation
# https://docs.djangoproject.com/en/1.11/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS": {"max_similarity": 1, "user_attributes": ["email"]},
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "accounts.validators.OneDigitPasswordValidator"},
    {"NAME": "accounts.validators.OneUpperPasswordValidator"},
    {"NAME": "accounts.validators.OneLowerPasswordValidator"},
]

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "guardian.backends.ObjectPermissionBackend",
    "accounts.backends.PhoneAuthBackend",
]

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": _required_env("REDIS_URL"),
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}

DEFAULT_FILE_STORAGE = "cozmo.storages.DOStorage"

DEFAULT_FROM_EMAIL = "Voyajoy <noreply@voyajoy.com>"
EMAIL_BACKEND = "sgbackend.SendGridBackend"

LANGUAGE_CODE = "en-us"

LOGIN_REDIRECT_URL = "/"

MEDIA_ROOT = os.path.join(BASE_DIR, "files", "media")

# SESSION_ENGINE = "django.contrib.sessions.backends.cache"
# SESSION_CACHE_ALIAS = "default"

SILENCED_SYSTEM_CHECKS = [
    "rest_framework.W001"  # DRF complaining that DEFAULT_PAGINATION_CLASS is None
]
SITE_ID = 1

STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "files", "static")

TEST_RUNNER = "xmlrunner.extra.djangotestrunner.XMLTestRunner"
TEST_OUTPUT_DIR = "test_reports/django"

TIME_ZONE = "UTC"  # DO NOT CHANGE


USE_I18N = True
USE_L10N = True
USE_TZ = True

CELERY_BROKER_URL = _required_env("REDIS_URL")
if CELERY_BROKER_URL.startswith("rediss://"):
    # celery[redis] does not support rediss:// URL scheme yet
    # issue on GitHub: https://github.com/celery/celery/issues/2833
    CELERY_BROKER_URL = CELERY_BROKER_URL.replace("rediss", "redis")
    ssl_conf = {"ssl_cert_reqs": ssl.CERT_NONE}
    CELERY_BROKER_USE_SSL = ssl_conf
    CELERY_REDIS_BACKEND_USE_SSL = ssl_conf
BROKER_URL = CELERY_BROKER_URL
CELERY_ACCEPT_CONTENT = ["application/json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_TASK_ROUTES = {"rental_network.tasks.*": {"queue": "selenium"}}
CELERY_ROUTES = {"rental_network.tasks.*": {"queue": "selenium"}}

# Cozmo
PROFILER = {}
AIRBNB_ID = "3945gczqpi169jtyaouwzknrs"
AIRBNB_SECRET = _required_env("AIRBNB_SECRET")
BOOKING_CLIENT_SECRET = _required_env("BOOKING_CLIENT_SECRET")
BOOKING_CLIENT_USERNAME = _required_env("BOOKING_CLIENT_USERNAME")
# BOOKING_CLIENT_ID = _required_env("BOOKING_CLIENT_ID")
COZMO_WEB_URL = "https://cozmo.voyajoy.com/"
LOGDNA_SECRET = _required_env("LOGDNA_SECRET")
SLACK_ID = _required_env("SLACK_CLIENT_ID")
SLACK_SECRET = _required_env("SLACK_SECRET")
STRIPE_SECRET = _required_env("STRIPE_SECRET")
STRIPE_WEBHOOK_SIGNATURE = _required_env("STRIPE_WEBHOOK_SIGNATURE")
ICALL_MAGIC_TRIAL_PERIOD = int(_required_env("ICALL_MAGIC_TRIAL_PERIOD"))
MAILCHIMP_ID = "259793043788"
MAILCHIMP_SECRET = _required_env("MAILCHIMP_SECRET")
PLAID_CLIENT_ID = "58ebfcafbdc6a40edcf7e5cf"
PLAID_SECRET = os.getenv("PLAID_SECRET")
PLAID_PUBLIC_KEY = "fd5e0b1857dd788a581ca6e6c66977"
PLAID_ENV = os.getenv("PLAID_ENV", "sandbox")
TWILIO = {"ACCOUNT": "AC64fe41259eca5f10675a01174e5a1147", "TOKEN": _required_env("TWILIO_SECRET")}
NEXMO = {
    "KEY": _required_env("NEXMO_KEY"),
    "SECRET": _required_env("NEXMO_SECRET"),
    "DEFAULT_FROM": _required_env("NEXMO_DEFAULT_NUMBER"),
    "URL": "https://rest.nexmo.com/sms/json",
}
YELP_ID = "4Q7JTeOb-O2ev-40b7y-0w"
YELP_SECRET = _required_env("YELP_SECRET")

TRIPADVISOR_URL = _required_env("TRIPADVISOR_URL")
TRIPADVISOR_CLIENT_ID = _required_env("TRIPADVISOR_CLIENT_ID")
TRIPADVISOR_SECRET_KEY = _required_env("TRIPADVISOR_SECRET_KEY")
# drf
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "accounts.authentication.PublicJWTAuthentication",
        "accounts.authentication.ShadowJWTAuthentication",
        "rest_framework_jwt.authentication.JSONWebTokenAuthentication",
        "accounts.authentication.APITokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PARSER_CLASSES": ("rest_framework.parsers.JSONParser",),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
        # "accounts.permissions.HasApplicationAccess",
        # "cozmo_common.permissions.ApplicationModelPermissions",
        # "accounts.permissions.GroupAccess",
    ),
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_THROTTLE_RATES": {"burst": "200/min", "sustained": "6000/hour"},
    "JSON_UNDERSCOREIZE": {"no_underscore_before_number": True},
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    "PAGE_SIZE": 20,
}

# allauth
ACCOUNT_ADAPTER = "accounts.adapter.AccountAdapter"
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = "optional"
ACCOUNT_EMAIL_SUBJECT_PREFIX = ""
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_SIGNUP_PASSWORD_ENTER_TWICE = False
ACCOUNT_UNIQUE_EMAIL = True
EMAIL_CONFIRMATION_EXPIRE_DAYS = 0
SOCIALACCOUNT_ADAPTER = "accounts.adapter.SocialAccountAdapter"
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"

# rest-auth
REST_USE_JWT = True
REST_AUTH_SERIALIZERS = {
    "USER_DETAILS_SERIALIZER": "accounts.profile.serializers.UserPlanSerializer",
    "PASSWORD_RESET_SERIALIZER": "accounts.serializers.PasswordResetSerializer",
    "PASSWORD_RESET_CONFIRM_SERIALIZER": "accounts.serializers.PasswordResetConfirmSerializer",
}
OLD_PASSWORD_FIELD_ENABLED = True
REST_AUTH_REGISTER_SERIALIZERS = {"REGISTER_SERIALIZER": "accounts.serializers.RegisterSerializer"}

# drf-ext
REST_FRAMEWORK_EXTENSIONS = {"DEFAULT_PARENT_LOOKUP_KWARG_NAME_PREFIX": ""}

# drf-yasg
SWAGGER_SETTINGS = {
    "SECURITY_DEFINITIONS": {
        "api_key": {"type": "apiKey", "in": "header", "name": "Authorization"}
    },
    "LOGIN_URL": "rest_framework:login",
    "LOGOUT_URL": "rest_framework:logout",
    "VALIDATOR_URL": None,
    "DOC_EXPANSION": "none",
}

# drf-jwt
JWT_AUTH = {"JWT_EXPIRATION_DELTA": timedelta(weeks=1)}

# sendgrid
SENDGRID_API_KEY = _required_env("SENDGRID_API")

# storages
AZURE_ACCOUNT_NAME = "cozmostorage"
AZURE_ACCOUNT_KEY = _required_env("AZ_STORAGE_KEY")
AZURE_CONTAINER = "cozmo"

# DO Spaces
AWS_ACCESS_KEY_ID = _required_env("DO_STORAGE_KEY")
AWS_SECRET_ACCESS_KEY = _required_env("DO_STORAGE_SECRET")
AWS_STORAGE_BUCKET_NAME = _required_env("DO_STORAGE_NAME")
AWS_S3_ENDPOINT_URL = _required_env("DO_STORAGE_URL")
AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
AWS_LOCATION = _required_env("DO_STORAGE_LOCATION")
AWS_DEFAULT_ACL = None

CDN_BASE_URL = _required_env("CDN_BASE_URL")

CDN_URL = f"{CDN_BASE_URL}/{AWS_STORAGE_BUCKET_NAME}/{AWS_LOCATION}"

MAX_GLOBAL_SEARCH_RESULTS = 5

DEFAULT_EMAIL_SENDER = "support@voyajoy.com"

DIALOGFLOW = {"PROJECT_ID": "newagent-73ea2"}

GOOGLE_API_KEY = _required_env("GOOGLE_API_KEY")

SELENIUM_HUB_URL = _required_env("SELENIUM_HUB_URL")
SELENIUM_HUB_PORT = _required_env("SELENIUM_HUB_PORT")

TWO_CAPTCHA_API_KEY = _required_env("TWO_CAPTCHA_API_KEY")
APARTMENTS_SITE_KEY = _required_env("APARTMENTS_SITE_KEY")
ZILLOW_SITE_KEY = _required_env("ZILLOW_SITE_KEY")

LONG_TERM_CHANNELS_ENABLED = _required_env("LONG_TERM_CHANNELS_ENABLED") == "True"

DEFAULT_SMART_PRICING_DAYS = 365

INVITATION_EXPIRY_DAYS = 7

APP_USER_PERMS = {
    "owner": {"owners": ["owner"]},
    "reservation": {"listings": ["reservation", "reservationnote"]},
    "vendor": {"vendors": ["assignment", "job", "report", "vendor", "worklog"]},
}

USER_ROLES = {
    "default": {},
    "owner": {
        "accounts": {
            "user": ["view", "add", "change", "delete"],
            "organization": ["change", "delete"],
        },
        "automation": {"reservationautomation": ["view", "add", "change", "delete"]},
        "listings": {
            "group": ["view", "add", "change", "delete"],
            "property": ["view", "add", "change", "delete"],
            "reservation": ["view", "add", "change", "delete"],
            "reservationnote": ["view", "add", "change", "delete"],
        },
        "owners": {"owner": ["view", "add", "change", "delete"]},
        "payments": {"subscription": ["view", "add", "change", "delete"]},
        "rental_connections": {"rentalconnection": ["view", "add", "change", "delete"]},
        "send_mail": {
            "conversation": ["view", "add", "change"],
            "message": ["view", "add"],
            "forwardingemail": ["view", "add", "change", "delete"]
        },
        "settings": {"organizationsettings": ["add", "change", "view"]},
        "vendors": {
            "assignment": ["view", "add", "change", "delete"],
            "job": ["view", "add", "change", "delete"],
            "report": ["view"],
            "vendor": ["view", "add", "change", "delete"],
            "worklog": ["view"],
        },
    },
    "admin": {
        "accounts": {
            "user": ["view", "add", "change", "delete"],
            "organization": ["change"],
        },
        "automation": {"reservationautomation": ["view", "add", "change", "delete"]},
        "listings": {
            "group": ["view", "add", "change", "delete"],
            "property": ["view", "add", "change", "delete"],
            "reservation": ["view", "add", "change", "delete"],
            "reservationnote": ["view", "add", "change", "delete"],
        },
        "owners": {"owner": ["view", "add", "change", "delete"]},
        "payments": {"subscription": ["view", "add", "change", "delete"]},
        "rental_connections": {"rentalconnection": ["view", "add", "change", "delete"]},
        "send_mail": {
            "conversation": ["view", "add", "change"],
            "message": ["view", "add"],
            "forwardingemail": ["view", "add", "change", "delete"]
        },
        "settings": {"organizationsettings": ["add", "change", "view"]},
        "vendors": {
            "assignment": ["view", "add", "change", "delete"],
            "job": ["view", "add", "change", "delete"],
            "report": ["view"],
            "vendor": ["view", "add", "change", "delete"],
            "worklog": ["view"],
        },
    },
    "agent": {
        "automation": {"reservationautomation": ["view", "add", "change", "delete"]},
        "listings": {
            "property": ["view", "add", "change"],
            "reservation": ["view", "add", "change", "delete"],
            "reservationnote": ["view", "add", "change", "delete"],
        },
        "send_mail": {"conversation": ["view", "add", "change"], "message": ["view", "add"]},
        "vendors": {
            "assignment": ["view", "add", "change", "delete"],
            "job": ["view", "add", "change", "delete"],
            "report": ["view"],
            "vendor": ["view", "add", "change", "delete"],
            "worklog": ["view"],
        },
    },
    "vendor": {
        "vendors": {"job": ["view", "change"], "report": ["view", "add", "change", "delete"]}
    },
}

SUBSCRIPTION_PLANS = {
    "free": {
        "plan_id": "plan_FncTFFDBGecKcH",
        "product_id": "prod_FnCjDGTbg744PI",
        "trial_period_days": 0,
    },
    "base": {
        "plan_id": "plan_FnCk9JmlA8wuxG",
        "product_id": "prod_FnCjDGTbg744PI",
        "trial_period_days": 14,
    },
}

# APP_SERIALIZERS = {
#     "ORGANIZATION_SUBSCRIPTION_SERIALIZER": "payments.serializers.IsSubscribedSerializer"
# }

APP_NAME = "Voyajoy"

PARSE_EMAIL_TASK_DB_TTL = 60
PARSE_EMAIL_DOMAIN = "emails.voyajoy.com"
PARSE_EMAIL_ENABLED = True

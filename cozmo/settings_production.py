from .settings_base import *  # noqa: F403

ENV_TYPE = "production"

ALLOWED_HOSTS = ["cozmo-api.voyajoy.com", "api-cozmo.voyajoy.com"]  # XXX Remove after DNS change

DATABASES["default"]["USER"] += "@db-cozmo"
DATABASES["default"]["HOST"] = "db-cozmo.postgres.database.azure.com"
DATABASES["default"]["OPTIONS"] = {"sslmode": "require"}

COZMO_CALENDAR_URL = "https://api-cozmo.voyajoy.com/calendars/{id}/ical/"
COZMO_WEB_URL = "https://cozmo.voyajoy.com/"

SUBSCRIPTION_PLANS = {
    "free": {
        "plan_id": "plan_FpWBb7GTQenrn4",
        "product_id": "prod_FpW94QHSmCpMWm",
        "trial_period_days": 0
    },
    "base": {
        "plan_id": "plan_FpWAr2whCfLxEL",
        "product_id": "prod_FpW94QHSmCpMWm",
        "trial_period_days": 14
    }
}
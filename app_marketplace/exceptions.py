class ServiceError(Exception):
    """Base Service exception."""


class SlackError(ServiceError):
    """Base Slack exception."""


class StripeError(ServiceError):
    """Base Stripe exception."""

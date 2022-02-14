from cozmo_common.enums import IntChoicesEnum


class PlanType(IntChoicesEnum):
    free = 1337
    base = 1


class SubscriptionStatus(IntChoicesEnum):
    in_trial = 1
    past_due = 2
    cancelled = 3

from cozmo_common.enums import ChoicesEnum, IntChoicesEnum


class Plan(ChoicesEnum):
    SINGLE = "single"
    SMALL = "small"
    ENTERPRISE = "enterprise"


class PaymentSchedule(IntChoicesEnum):
    at_booking = 0
    at_check_in = 1
    days_before_1 = 101
    days_before_7 = 107
    days_before_14 = 114
    days_before_60 = 160
    days_before_90 = 190


class PaymentTemplate(IntChoicesEnum):
    payment_100 = 1
    payment_50_50 = 2
    payment_33_33_34 = 3

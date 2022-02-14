from cozmo_common.enums import IntChoicesEnum


class EventType(IntChoicesEnum):
    Inquiry = 0
    Agreement_signed = 1
    Agreement_rejected = 2
    Agreement_sent = 3
    Quote_sent = 4
    Reservation_created = 5
    Reservation_modified = 6
    Reservation_cancelled = 7
    Reservation_cancellation_request = 8
    Notes_changed = 9
    Message_received = 10
    Message_sent = 11
    Welcome_letter_sent = 12
    Reminder_sent = 13
    Payment = 20
    Refund = 21
    Dispute = 22

    Model_created = 30
    Model_modified = 31
    Model_deleted = 32

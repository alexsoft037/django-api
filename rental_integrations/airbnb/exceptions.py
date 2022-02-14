from rest_framework import serializers


class NoChildrenDetailsValidationError(serializers.ValidationError):
    def __init__(self):
        super().__init__(
            "allows_children_as_host is true, children_not_allowed_details should be provided"
        )


class AdvancedNoticeInvalidValueValidationError(serializers.ValidationError):
    def __init__(self):
        super().__init__(
            "Advanced notice value is not part of the allowed set: [0-24, 48, 72, 168]"
        )

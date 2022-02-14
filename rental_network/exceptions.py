from rest_framework import serializers


class ServiceException(Exception):
    def __init__(self, *args, **kwargs):
        super(ServiceException, self).__init__(*args)
        for k, v in kwargs.items():
            setattr(self, k, v)


class AuthenticationFailedException(ServiceException):
    DEFAULT = 0
    AUTH_CHALLENGE = 1

    def __init__(self, error_type=DEFAULT, data=dict(), *args, **kwargs):
        super(AuthenticationFailedException, self).__init__(*args, **kwargs)
        self.error_type = error_type
        self.data = data


class ListingRequirementValidationError(serializers.ValidationError):
    def __init__(self, details):
        super().__init__(details, code="listing_prerequisite")


class MinPhotoValidationError(ListingRequirementValidationError):
    def __init__(self):
        super().__init__("Listing does not have enough photos")


class MinHDPhotoValidationError(ListingRequirementValidationError):
    def __init__(self):
        super().__init__(f"Listing does not have enough HD photos")


class MinAmenitiesValidationError(ListingRequirementValidationError):
    def __init__(self):
        super().__init__("Listing does not have enough amenities")


class MinDescriptionValidationError(ListingRequirementValidationError):
    def __init__(self):
        super().__init__("Listing does not have enough description content")


class NoSTRLicenseValidationError(ListingRequirementValidationError):
    def __init__(self):
        super().__init__("Listing does not an STR license in the specified city")

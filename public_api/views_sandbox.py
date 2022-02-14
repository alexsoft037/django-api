from listings import models
from . import views


class PropertyViewSet(views.PropertyViewSet):

    queryset = models.Property.objects.sandbox().order_by("id")


class FeeViewSet(views.FeeViewSet):

    queryset = models.AdditionalFee.objects.sandbox()


class RateViewSet(views.RateViewSet):

    queryset = models.Rate.objects.sandbox()


class ReservationViewSet(views.ReservationViewSet):

    queryset = models.Reservation.objects.sandbox()


class QuoteViewSet(views.QuoteViewSet):
    pass


class StayRequirementsViewSet(views.StayRequirementsViewSet):

    queryset = models.Availability.objects.sandbox()

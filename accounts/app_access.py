from accounts.choices import ApplicationTypes

DEFAULT_APP = ApplicationTypes.iCal_Magic.value
DEFAULT_APPS = [ApplicationTypes.Reservation]

APP_ACCESS = {
    ApplicationTypes.iCal_Magic.value: {
        "accounts.profile.views": {"PlanSettingsView": {}},
        "listings.views": {
            "AvailabilityViewSet": {},
            "BlockingViewSet": {},
            "FeatureViewSet": {},
            "GroupViewSet": {},
            "ImageViewSet": {},
            "PointOfInterestViewSet": {},
            "PropertyViewSet": {},
            "ReservationCalendarView": {
                "serializer": ("listings.serializers", "PropertyCalMinSerializer")
            },
            "RoomViewSet": {},
            "TurndaysViewSet": {},
            "VideoViewSet": {},
        },
        "listings.calendars.views": {
            "CalendarColorViewSet": {},
            "CalendarViewSet": {},
            "ExternalCalendarEventViewSet": {},
            "ExternalCalendarViewSet": {},
        },
        "pois.views": {"PoiViewSet": {}},
        "rental_connections.views": {"RentalConnectionViewSet": {}},
        "rental_integrations.airbnb.views": {"AirbnbAccountViewSet": {}, "Airbnb2faViewSet": {}},
        "rental_integrations.booking.views": {"BookingViewSet": {}},
        "rental_integrations.expedia.views": {"ExpediaViewSet": {}},
        "rental_integrations.homeaway.views": {
            "HomeAwayAccountViewSet": {},
            "Homeaway2faViewSet": {},
        },
        "rental_integrations.trip_advisor.views": {"TripAdvisorSyncViewSet": {}},
        "search.views": {"SearchView": {}},
    },
    ApplicationTypes.Reservation.value: {
        "listings.views": {
            "ChargeView": {},
            "DiscountViewSet": {},
            "FeeViewSet": {},
            "QuoteViewSet": {},
            "ReservationCalendarView": {
                "serializer": ("listings.serializers", "PropertyCalSerializer")
            },
            "ReservationNoteViewSet": {},
            "ReservationViewSet": {},
            "RateViewSet": {},
            "SchedulingAssistantViewSet": {},
            "SeasonalRateViewSet": {},
            "TaxViewSet": {},
        },
        "payments.views": {
            "CreditCardViewSet": {},
            "GuestCreditCardViewSet": {},
            "PricingPlanViewSet": {},
            "SubscribeViewSet": {},
            "ChargeViewSet": {},
            "DisputeViewSet": {},
            "CouponViewSet": {},
        },
    },
}

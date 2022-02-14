from django.db import models
from django.db.models.expressions import Case, F, Value, When

from . import choices


class PropertyQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=choices.PropertyStatuses.Active)

    def with_coordinates(self):
        return self.filter(location__latitude__isnull=False, location__longitude__isnull=False)

    def with_cleaning_app_enabled(self):
        return self.filter(scheduling_assistant__enabled=True)

    def existing(self):
        return self.exclude(status=choices.PropertyStatuses.Removed)

    def list(self):
        return self.select_related("owner")


class FixedCaseQuerySet(models.QuerySet):
    def fixed_case(self, days, guests=0):
        return self.annotate(
            partial_value=Case(
                When(calculation_method=choices.CalculationMethod.Per_Stay.value, then="value"),
                When(
                    calculation_method=choices.CalculationMethod.Daily.value,
                    then=F("value") * Value(days),
                ),
                When(
                    calculation_method=choices.CalculationMethod.Per_Person_Per_Day.value,
                    then=F("value") * Value(days * guests),
                ),
                When(
                    calculation_method=choices.CalculationMethod.Per_Person_Per_Stay.value,
                    then=F("value") * Value(guests),
                ),
                default=0,
                output_field=models.DecimalField(),
            )
        )


class FeeTypeQuerySet(FixedCaseQuerySet):
    _fee_types = dict(choices.FeeTypes.choices()).keys()
    _tax_types = dict(choices.TaxTypes.choices()).keys()

    def fees(self):
        return self.filter(fee_tax_type__in=self._fee_types)

    def taxes(self):
        return self.filter(fee_tax_type__in=self._tax_types)


class HostedQuerySet(models.QuerySet):

    _external = models.Q(url__startswith="https://") | models.Q(url__startswith="http://")

    def self_hosted(self):
        return self.exclude(self._external)

    def externally_hosted(self):
        return self.filter(self._external)


class RateQuerySet(models.QuerySet):
    def default_rates(self):
        return self.filter(time_frame=(None, None))

    def seasonal_rates(self, time_frame, prop_id):
        return self.filter(
            prop_id=prop_id, seasonal=True, time_frame__overlap=time_frame
        ).order_by("-time_frame")

    def visit_rates(self, time_frame, prop_id):
        return self.filter(
            prop_id=prop_id, seasonal=False, time_frame__overlap=time_frame
        ).order_by("-time_frame")

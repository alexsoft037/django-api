from django.db.models import Manager

from .choices import FeeTypes, TaxTypes


class ProductionManager(Manager):
    def __init__(self, lookup_field="is_sandbox"):
        self.lookup_field = lookup_field
        super().__init__()

    def get_queryset(self):
        return super().get_queryset().filter(**{self.lookup_field: False})

    def sandbox(self):
        return super().get_queryset().filter(**{self.lookup_field: True})


class TaxManager(Manager):
    _taxes = [tax.value for tax in TaxTypes]

    def get_queryset(self):
        return super().get_queryset().filter(fee_tax_type__in=self._taxes)


class FeeManager(Manager):
    _fees = [fee.value for fee in FeeTypes]

    def get_queryset(self):
        return super().get_queryset().filter(fee_tax_type__in=self._fees)

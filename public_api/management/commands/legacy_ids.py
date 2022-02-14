import csv
import os.path

from django.core.management.base import BaseCommand

from listings.models import Property


class Command(BaseCommand):

    help = "Set legacy ID for a subset of imported Properties"

    def handle(self, *args, **options):
        verbosity = options["verbosity"]
        curr_dir = os.path.dirname(os.path.abspath(__file__))
        csv_name = f"{curr_dir}/legacy_ids.csv"
        total_updated = 0

        with open(csv_name, "r") as csv_file:
            ids_mapping = csv.reader(csv_file)
            for legacy_id, external_id in ids_mapping:
                queryset = Property.objects.filter(external_id=external_id)
                updated = queryset.update(legacy_id=legacy_id)
                total_updated += updated
                if verbosity > 2 or (verbosity > 1 and updated > 0):
                    message = f'Updated {updated} properties with external_id "{external_id}"'
                    self.stdout.write(message)

        if verbosity > 0:
            message = f"Updated {total_updated} properties with legacy ids"
            self.stdout.write(self.style.SUCCESS(message))

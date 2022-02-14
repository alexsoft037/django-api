from django.core.management.base import BaseCommand

from listings.models import Image


class Command(BaseCommand):

    help = "Generate thumbnails for self-hosted Images"

    def handle(self, *args, **options):
        for obj in Image.objects.self_hosted().filter(thumbnail=None):
            obj.generate_thumbnail()

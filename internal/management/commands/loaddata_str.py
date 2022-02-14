import warnings

from django.core import serializers
from django.core.management.base import CommandError
from django.core.management.commands import loaddata
from django.db import DatabaseError, IntegrityError, router
from django.utils.encoding import force_text
from future.builtins import super


class Command(loaddata.Command):
    """
    Loaddata to allow reading from string
    """

    def add_arguments(self, parser):
        super().add_arguments(parser)

        parser.add_argument(
            "--format",
            action="store",
            dest="format",
            default=None,
            help="Format when reading stdin",
        )
        parser.add_argument(
            "--str", action="store", dest="str", default=None, help="Load data from string"
        )

    def handle(self, *args, **options):
        self.format = options.get("format")
        self.str = options.get("str")

        return super().handle(*args, **options)

    def parse_name(self, fixture_name):
        self.compression_formats["string"] = (lambda x, y: self.str, None)

        if not self.format:
            raise CommandError("Must specify format when reading from string")

        return "-", self.format, "string"

    def find_fixtures(self, fixture_label):
        return [("-", None, "-")]

    def load_label(self, fixture_label):  # noqa: C901

        show_progress = self.verbosity >= 3
        _, ser_fmt, cmp_fmt = self.parse_name("-")
        open_method, mode = self.compression_formats[cmp_fmt]
        fixture = open_method("-", mode)
        try:
            self.fixture_count += 1
            objects_in_fixture = 0
            loaded_objects_in_fixture = 0
            print("self.verbosity", self.verbosity)
            if self.verbosity >= 2:
                self.stdout.write("Installing %s".format(ser_fmt))

            objects = serializers.deserialize(
                ser_fmt, fixture, using=self.using, ignorenonexistent=self.ignore
            )

            for obj in objects:
                objects_in_fixture += 1
                if (
                    obj.object._meta.app_config in self.excluded_apps
                    or type(obj.object) in self.excluded_models
                ):
                    continue
                if router.allow_migrate_model(self.using, obj.object.__class__):
                    loaded_objects_in_fixture += 1
                    self.models.add(obj.object.__class__)
                    try:
                        obj.save(using=self.using)
                        if show_progress:
                            self.stdout.write(
                                "\rProcessed {} object(s).".format(loaded_objects_in_fixture),
                                ending="",
                            )
                    except (DatabaseError, IntegrityError) as e:
                        e.args = "Could not load {app}s.{object_name}s(pk={pk}s): {error}s".format(
                            app=obj.object._meta.app_label,
                            object_name=obj.object._meta.object_name,
                            pk=obj.object.pk,
                            error=force_text(e),
                        )
                        raise
            if objects and show_progress:
                self.stdout.write("")  # add a newline after progress indicator
            self.loaded_object_count += loaded_objects_in_fixture
            self.fixture_object_count += objects_in_fixture
        except Exception as e:
            if not isinstance(e, CommandError):
                e.args = ("Problem installing fixture {}".format(e),)
            raise

        # Warn if the fixture we loaded contains 0 objects.
        if objects_in_fixture == 0:
            warnings.warn("No fixture data found.", RuntimeWarning)

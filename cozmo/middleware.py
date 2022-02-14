import pstats
from cProfile import Profile
from io import StringIO

from django.conf import settings
from django.http import HttpResponse


class cProfileMiddleware:
    # Based on https://github.com/someshchaturvedi/customizable-django-profiler

    def __init__(self, get_response):
        self.get_response = get_response
        self.profiler = Profile()

    def __call__(self, request):
        can_profile = self.can_profile(request)

        if can_profile:
            self.profiler.enable()

        response = self.get_response(request)

        if can_profile:
            self.profiler.create_stats()
            out = StringIO()
            stats = pstats.Stats(self.profiler, stream=out)
            stats.sort_stats(settings.PROFILER.get("sort", "time"))
            stats.print_stats(int(settings.PROFILER.get("count", 100)))
            result = out.getvalue()
            for output in settings.PROFILER.get("output", ["console"]):
                if output == "console":
                    print(result)
                if output == "file":
                    file_location = settings.PROFILER.get("file_location", "profile.txt")
                    print(file_location)
                    with open(file_location, "a+") as f:
                        f.write(result)
                if output == "response":
                    response = HttpResponse(result, content_type="application/liquid")
            self.profiler.dump_stats("profile.raw")
        return response

    def can_profile(self, request):
        if settings.DEBUG and settings.PROFILER["activate"]:
            trigger = settings.PROFILER.get("trigger", "all")
            can = trigger == "all" or trigger.split(":")[1] in request.GET
        else:

            can = False
        return can

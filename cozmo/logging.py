from django.conf import settings
from logdna import LogDNAHandler


class LogDNA(LogDNAHandler):
    def __init__(self, options={}):
        options.setdefault("hostname", "cozmo-{}".format(getattr(settings, "ENV_TYPE")))
        super(LogDNA, self).__init__(settings.LOGDNA_SECRET, options)

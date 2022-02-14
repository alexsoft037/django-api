import os

from django import template

register = template.Library()


@register.simple_tag
def cozmo_version():
    return os.environ.get("COZMO_VERSION", "")

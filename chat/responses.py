import logging

import yaml

logger = logging.getLogger(__name__)


def get_base_templates():
    templates = dict()
    try:
        f = open(f"templates/base.yml", "rb")
        templates = yaml.load(f.read())
        f.close()
    except FileNotFoundError as e:
        pass
    return templates


def get_template(name, sub):
    template = None
    templates = get_base_templates()
    try:
        f = open("chat/templates/responses/{}.yml".format(name.replace("-", "_")), "rb")
        templates.update(yaml.load(f.read()))
        items = templates.get(sub)
        template = items[0] if items else None
        f.close()
    except FileNotFoundError as e:
        pass
    return template

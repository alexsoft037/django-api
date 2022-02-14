import re


def html_to_text(html):
    br = "<br />"
    clean = re.compile("<.*?>")
    return re.sub(clean, "", html.replace(br, "\n"))

import datetime as dt
import logging
import re
import string
from collections import ChainMap
from email.header import decode_header
from itertools import chain
from urllib import parse

from celery.task import periodic_task
from lxml import etree, html
from requests import RequestException

from app_marketplace.models import GoogleApp
from app_marketplace.services import Airbnb, Google
from rental_integrations.airbnb.models import AirbnbAccount

logger = logging.getLogger(__name__)


@periodic_task(run_every=dt.timedelta(hours=12))
def refresh_airbnb_token():
    airbnb = Airbnb()
    for acc in AirbnbAccount.objects.all().only("id", "refresh_token"):
        try:
            response = airbnb.refresh_token(acc.refresh_token)
        except RequestException:
            continue
        acc.access_token = response["access_token"]
        acc.refresh_token = response.get("refresh_token", acc.refresh_token)
        acc.user_id = response["user_id"]
        acc.save()


_re_patterns = {
    "airbnb": {
        "subject": [
            re.compile(
                "".join(
                    (
                        r"Reservation confirmed - ",
                        r"(?P<guest_name>[\w {}]+) ".format(string.punctuation),
                        r"arrives (?P<start_date>\w{3} \d{1,2})",
                    )
                ),
                re.UNICODE,
            )
        ],
        "body": [
            re.compile(r"(?P<days>\d+) nights?\s+\$ ?(?P<price>\d+\.\d{2})", re.MULTILINE),
            re.compile(r"\scleaning fees\s+\$ ?(?P<cleaning_fee>\d+\.\d{2})", re.MULTILINE),
            # '−' in following regex is '\u2212', not regular '-'
            re.compile(r"\sairbnb fees\s+−\$ ?(?P<airbnb_fee>\d+\.\d{2})", re.MULTILINE),
            re.compile(r"\sguests\s+(?P<guests>\d+)", re.MULTILINE),
        ],
    },
    "homeaway": [
        re.compile(r"\sproperty\s+#(?P<property_id>\d+)", re.MULTILINE),
        re.compile(r"\sreservation id\s+(?P<reservation_id>[-\w]+)\s+", re.MULTILINE),
        re.compile(r"\straveler phone\s+(?P<guest_phone>[-+\d() ]+)\s+", re.MULTILINE),
        re.compile(
            r"\sguests\s+(?P<guests_adults>\d+) adults?, (?P<guests_children>\d+) child(ren)?",
            re.MULTILINE,
        ),
        re.compile(
            r"\straveler name\s+(?P<guest_name>[\w {}]+)\s+".format(string.punctuation),
            re.MULTILINE | re.UNICODE,
        ),
        re.compile(
            "".join(
                (
                    r"\sdates\s+(?P<start_date>\w{3} \d{1,2})-",
                    r"(?P<end_date>(\w{3} )?\d{1,2}), ",
                    r"(?P<start_year>\d{4})",
                )
            ),
            re.MULTILINE,
        ),
        re.compile(r"\straveler payment:?\s+\$(?P<price>\d+\.\d{2})", re.MULTILINE),
        re.compile(r"\spayment to you:?\s+\$(?P<price_net>\d+\.\d{2})", re.MULTILINE),
    ],
}


def _parse_homeaway_email(message, now):
    try:
        m_html = [m for m in message.walk() if m.get_content_type() == "text/html"][0]
        root = html.fromstring(m_html.get_payload(decode=True))
        e = root.xpath('//td[contains(@class, "panel-bce")]')[0]
    except IndexError:
        logger.info("Incorrect email format: %s, id: %s!", message["From"], message["Message-ID"])
        return {}

    etree.strip_elements(e, "style", "img", "meta")
    etree.strip_attributes(e, "style")
    details = e.text_content().strip().lower()

    results = ChainMap(
        *(
            p.groupdict(default=None)
            for p in (pattern.search(details) for pattern in _re_patterns["homeaway"])
            if p
        )
    )

    if None in results.values():
        logger.info("Missing re values: %s", results)
        return {}

    results["guest_name"] = results["guest_name"].title()
    then = dt.datetime.strptime(now, "%Y-%m-%d").date()
    start_date = (
        dt.datetime.strptime(results["start_date"], "%b %d").date().replace(year=then.year)
    )
    try:
        end_date = (
            dt.datetime.strptime(results["end_date"], "%b %d").date().replace(year=then.year)
        )
    except ValueError:
        end_date = (
            dt.datetime.strptime(results["end_date"], "%d")
            .date()
            .replace(year=then.year, month=start_date.month)
        )

    if then > start_date:
        start_date = start_date.replace(year=then.year + 1)
    if start_date > end_date:
        end_date = end_date.replace(yeat=start_date.year + 1)

    return {**results, "user_id": None, "start_date": start_date, "end_date": end_date}


def _parse_airbnb_email(message, now):
    try:
        m_html = [m for m in message.get_payload() if m.get_content_type() == "text/html"][0]
    except IndexError:
        logger.info("Incorrect email format: %s, id: %s!", message["From"], message["Message-ID"])
        return {}

    e = html.fromstring(m_html.get_payload(decode=True))
    etree.strip_elements(e, "style", "img", "meta")
    etree.strip_attributes(e, "style")

    try:
        user_url, *_ = e.xpath('//a[contains(@href, "airbnb.com/users/")]/@href')
        user_id = parse.parse_qs(parse.urlsplit(user_url).query)["id"][0]
    except (KeyError, ValueError):
        user_id = None

    try:
        a, *_ = e.xpath('//table[contains(@class, "destination-card")]//a')
        url = a.attrib["href"]
        name, *_ = a.xpath(
            './p[not(contains(@class, "subheadline")) and ' 'contains(@class, "headline")]/text()'
        )
        prop_data = {
            "property_name": name.replace("›", "").strip(),
            "property_id": parse.parse_qs(parse.urlsplit(url).query)["id"][0],
        }
    except (KeyError, ValueError):
        logger.info("No url, name or id: %s, id: %s", message["From"], message["Message-ID"])
        return {}

    details = e.text_content().strip().lower()

    subject, encoding = decode_header(message["Subject"])[0]
    if encoding:
        subject = subject.decode(encoding)

    results = ChainMap(
        *(
            p.groupdict(default=None)
            for p in chain(
                (pattern.search(subject) for pattern in _re_patterns["airbnb"]["subject"]),
                (pattern.search(details) for pattern in _re_patterns["airbnb"]["body"]),
            )
            if p
        )
    )

    if None in results.values():
        logger.info("Missing re values: %s", results)
        return {}

    then = dt.datetime.strptime(now, "%Y-%m-%d").date()
    start_date = (
        dt.datetime.strptime(results["start_date"], "%b %d").date().replace(year=then.year)
    )
    if then > start_date:
        start_date = start_date.replace(year=then.year + 1)

    return {
        **results,
        **prop_data,
        "user_id": user_id,
        "start_date": start_date,
        "end_date": start_date + dt.timedelta(days=int(results["days"])),
    }


def _parse_booking_email(message, now):
    try:
        m_html = [m for m in message.walk() if m.get_content_type() == "text/html"][0]
        e = html.fromstring(m_html.get_payload(decode=True))
        url, *_ = e.xpath('//a[starts-with(@href, "https://admin.booking.com/")]/@href')
        query_params = parse.parse_qs(parse.urlsplit(url).query)
        results = {
            "reservation_id": query_params["res_id"][0],
            "property_id": query_params["hotel_id"][0],
        }
    except IndexError:
        logger.info("Incorrect email format: %s, id: %s!", message["From"], message["Message-ID"])
        results = {}
    except ValueError:
        logger.info("Admin link not present: %s, id: %s!", message["From"], message["Message-ID"])
        results = {}
    except KeyError:
        logger.info(
            "Admin link does not have res_id or hotel_id: %s, id: %s!",
            message["From"],
            message["Message-ID"],
        )
        results = {}

    subject, encoding = decode_header(message["Subject"])[0]
    if encoding:
        subject = subject.decode(encoding)

    match = _re_patterns["booking"].search(subject)
    if match:
        results["start_date"] = dt.datetime.strptime(match["date"], "%d %B %Y").date()

    return results


def aribnb_reservations(google_app_id, after):
    def is_from_airbnb(message):
        return message.get("X-Original-Sender", "").strip().endswith("@airbnb.com")

    query_params = {"query": "airbnb new reservation confirmed", "after": after}

    try:
        ga = GoogleApp.objects.get(id=google_app_id)
    except GoogleApp.DoesNotExist:
        return

    service = Google(ga.credentials)
    messages = (m for m in service.get_messages(query_params=query_params) if is_from_airbnb(m))
    return [_parse_airbnb_email(m, after) for m in messages]


def booking_reservations(google_app_id, after):
    def is_from_booking(message):
        return message.get("Sender", "").strip().endswith("@booking.com>")

    query_params = {"from": "booking", "subject": "new booking", "after": after}

    try:
        ga = GoogleApp.objects.get(id=google_app_id)
    except GoogleApp.DoesNotExist:
        return

    service = Google(ga.credentials)
    messages = (m for m in service.get_messages(query_params=query_params) if is_from_booking(m))
    return [_parse_booking_email(m, after) for m in messages]


def homeaway_reservations(google_app_id, after):
    def is_from_homeaway(message):
        return message.get("X-Original-Sender", "").strip().endswith("homeaway.com")

    query_params = {"from": "homeaway", "subject": "instant booking", "after": after}

    try:
        ga = GoogleApp.objects.get(id=google_app_id)
    except GoogleApp.DoesNotExist:
        return

    service = Google(ga.credentials)
    messages = (m for m in service.get_messages(query_params=query_params) if is_from_homeaway(m))
    return [_parse_homeaway_email(m, after) for m in messages]

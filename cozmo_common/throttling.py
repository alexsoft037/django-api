from contextlib import contextmanager
from typing import List

from django.conf import settings
from django.utils import timezone
from django_redis import get_redis_connection


class ThrottlingError(Exception):
    pass


class RateLimit:
    def __init__(self, name: str, window: "datetime.timedelta", max_calls: int):
        self.key = f"throttle:env:{name}"
        self.window = window
        self.max_calls = max_calls
        self.conn = get_redis_connection("default")

    def is_allowed(self, call_time: "datetime.datetime") -> bool:
        timestamp = call_time.timestamp()

        with self.conn.pipeline():
            self.conn.zremrangebyscore(self.key, 0, (call_time - self.window).timestamp())
            self.conn.expire(self.key, self.window)
            calls_made = self.conn.zcount(self.key, 0, timestamp)
        return calls_made < self.max_calls

    def add_call(self, call_time: "datetime.datetime"):
        timestamp = call_time.timestamp()
        self.conn.zadd(self.key, timestamp, timestamp)

    def __eq__(self, other):
        if isinstance(other, RateLimit):
            return self.key == other.key
        return NotImplemented

    def __hash__(self):
        return hash(self.key)


@contextmanager
def check_throttling(rate_limits: List[RateLimit]):
    call_time = timezone.now()

    if not all(limit.is_allowed(call_time) for limit in rate_limits):
        raise ThrottlingError()  # FIXME

    yield

    for limit in rate_limits:
        limit.add_call(call_time)

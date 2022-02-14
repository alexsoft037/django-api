from decimal import Decimal
from types import GeneratorType


def strip_falsy(d: dict) -> dict:
    def exclude_none(iterable):
        return [e for e in iterable if e or isinstance(e, bool)]

    def is_truthy(v):
        if any(
            (
                isinstance(v, (int, float, bool, Decimal, GeneratorType)),
                isinstance(v, (str, bytes)) and v,
                isinstance(v, dict) and exclude_none(v.values()),
                isinstance(v, (list, tuple, set)) and exclude_none(v),
            )
        ):
            truthy = True
        else:
            truthy = False
        return truthy

    return {k: v for k, v in d.items() if is_truthy(v)}

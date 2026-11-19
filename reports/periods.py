"""The period of a report, from the URL query, and the comparison with the
period right before it.

    ?period=7 | 30 | 90          the last N days, today included
    ?from=2026-11-01&to=2026-11-19   any period, both days included

    period 2026-11-01 .. 2026-11-19 (19 days)
    previous      2026-10-13 .. 2026-10-31 (the same 19 days right before)

The web pages, the CSV / XLSX exports and the REST API (stage 4.4) read the
period the same way, so one URL means the same numbers everywhere.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.utils.translation import gettext as _

from .days import today

PRESETS = (7, 30, 90)
DEFAULT_PRESET = 30
# A longer period would mean thousands of points on a chart and a slow page
MAX_DAYS = 366


class PeriodError(ValueError):
    """A period that can't be used; the text is for the user."""


@dataclass(frozen=True)
class Period:
    first: date
    last: date
    # 7 / 30 / 90 when chosen by a button, None for a custom period
    preset: int | None = None

    @property
    def days(self):
        return (self.last - self.first).days + 1

    @property
    def previous(self):
        """The period of the same length that ends the day before this one."""
        last = self.first - timedelta(days=1)
        return Period(last - timedelta(days=self.days - 1), last)

    def as_params(self):
        """The query of this period: for links, exports and cache keys."""
        if self.preset:
            return {"period": str(self.preset)}
        return {"from": self.first.isoformat(), "to": self.last.isoformat()}


def preset_period(days, *, until=None):
    last = until or today()
    return Period(last - timedelta(days=days - 1), last, preset=days)


def parse_period(query, *, until=None):
    """A Period from a QueryDict (request.GET) or a dict; PeriodError if bad.

    from / to win over period: a custom period from the date fields.
    """
    if query.get("from") or query.get("to"):
        return parse_custom(query.get("from", ""), query.get("to", ""))

    raw = query.get("period") or str(DEFAULT_PRESET)
    try:
        days = int(raw)
    except ValueError:
        days = None
    if days not in PRESETS:
        raise PeriodError(_("Unknown period: %(value)s.") % {"value": raw})
    return preset_period(days, until=until)


def parse_custom(first_text, last_text):
    try:
        first = date.fromisoformat(first_text)
        last = date.fromisoformat(last_text)
    except ValueError:
        raise PeriodError(_("Enter both dates as YYYY-MM-DD.")) from None
    if first > last:
        raise PeriodError(_("The start of the period is later than its end."))
    period = Period(first, last)
    if period.days > MAX_DAYS:
        raise PeriodError(_("The period is too long: at most %(days)d days.") % {"days": MAX_DAYS})
    return period


def compare(current, previous):
    """A value against the previous period: for the arrow and the percent.

    percent is None when the previous value is 0: "+100%" or "+infinity"
    would both be misleading, the page shows "new" instead.
    """
    current = current or 0
    previous = previous or 0
    if current > previous:
        direction = "up"
    elif current < previous:
        direction = "down"
    else:
        direction = "same"
    percent = None
    if previous:
        percent = round((Decimal(current) - Decimal(previous)) / Decimal(previous) * 100, 1)
    return {"value": current, "previous": previous, "direction": direction, "percent": percent}

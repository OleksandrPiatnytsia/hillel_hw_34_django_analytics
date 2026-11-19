"""The calendar day of the reports: a day in Kyiv, not in UTC.

The database keeps every moment in UTC (TIME_ZONE = "UTC"), but the shop and
its managers live in Kyiv. An order placed at 01:30 in Kyiv is 23:30 UTC of
the day BEFORE; counted by UTC, it would land in the wrong day of a report.
So a report day is cut by REPORTS_TIME_ZONE:

    day 2026-11-19 (Kyiv, UTC+2 in winter)
        = from 2026-11-18 22:00 UTC up to (not including) 2026-11-19 22:00 UTC

The bounds come from zoneinfo, so the summer time (UTC+3) and the two days a
year with 23 and 25 hours are handled without our own arithmetic.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone


def report_zone():
    return ZoneInfo(settings.REPORTS_TIME_ZONE)


def local_day(moment):
    """The report day of a moment (an aware datetime from the database)."""
    return moment.astimezone(report_zone()).date()


def today():
    return local_day(timezone.now())


def day_bounds(day):
    """(start, end) of a report day in UTC; end is not included.

    Both are midnights in Kyiv: the start of this day and of the next one.
    Not start + 24 hours: a day of the clock change is 23 or 25 hours long.
    Returned in UTC because Python subtracts two datetimes of the SAME zone
    by the wall clock (always 24 hours); in UTC the length is the real one.
    """
    zone = report_zone()
    start = datetime.combine(day, time.min, tzinfo=zone)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return start.astimezone(UTC), end.astimezone(UTC)


def days_between(first, last):
    """Every day from first to last, both included."""
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


def parse_day(text):
    """ "2026-11-19" -> date; ValueError for anything else."""
    return date.fromisoformat(text)

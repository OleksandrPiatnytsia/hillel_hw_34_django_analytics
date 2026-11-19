"""The Kyiv day of the reports (reports/days.py): no database needed."""

from datetime import date, datetime, timedelta, timezone

import pytest

from reports.days import day_bounds, days_between, local_day, parse_day


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_late_evening_utc_is_the_next_day_in_kyiv():
    # 22:30 UTC = 00:30 in Kyiv (UTC+2 in November)
    assert local_day(utc(2026, 11, 18, 22, 30)) == date(2026, 11, 19)
    assert local_day(utc(2026, 11, 18, 21, 59)) == date(2026, 11, 18)


def test_winter_day_starts_at_22_utc():
    start, end = day_bounds(date(2026, 11, 19))
    assert start == utc(2026, 11, 18, 22, 0)
    assert end == utc(2026, 11, 19, 22, 0)


def test_summer_day_starts_at_21_utc():
    start, _end = day_bounds(date(2026, 7, 1))
    assert start == utc(2026, 6, 30, 21, 0)


@pytest.mark.parametrize(
    "day, hours",
    [
        # The last Sunday of March: clocks go forward, the day is 23 hours
        (date(2026, 3, 29), 23),
        # The last Sunday of October: clocks go back, the day is 25 hours
        (date(2026, 10, 25), 25),
        (date(2026, 11, 19), 24),
    ],
)
def test_day_length_follows_the_clock_change(day, hours):
    start, end = day_bounds(day)
    assert end - start == timedelta(hours=hours)


def test_days_between_includes_both_ends():
    assert days_between(date(2026, 11, 1), date(2026, 11, 3)) == [
        date(2026, 11, 1),
        date(2026, 11, 2),
        date(2026, 11, 3),
    ]
    assert days_between(date(2026, 11, 3), date(2026, 11, 1)) == []


def test_parse_day():
    assert parse_day("2026-11-19") == date(2026, 11, 19)
    with pytest.raises(ValueError):
        parse_day("19.11.2026")

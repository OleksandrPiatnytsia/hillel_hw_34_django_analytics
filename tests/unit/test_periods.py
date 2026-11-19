"""The period of a report from the URL and the comparison (reports/periods.py)."""

from datetime import date
from decimal import Decimal

import pytest

from reports.periods import MAX_DAYS, Period, PeriodError, compare, parse_period

TODAY = date(2026, 11, 19)


def test_default_is_the_last_30_days():
    period = parse_period({}, until=TODAY)

    assert period == Period(date(2026, 10, 21), TODAY, preset=30)
    assert period.days == 30
    assert period.as_params() == {"period": "30"}


def test_preset():
    period = parse_period({"period": "7"}, until=TODAY)

    assert period.first == date(2026, 11, 13)
    assert period.days == 7


@pytest.mark.parametrize("value", ["5", "abc", "-7"])
def test_unknown_preset(value):
    with pytest.raises(PeriodError):
        parse_period({"period": value}, until=TODAY)


def test_custom_period_wins_over_the_preset():
    period = parse_period({"period": "7", "from": "2026-11-01", "to": "2026-11-19"})

    assert period == Period(date(2026, 11, 1), TODAY)
    assert period.as_params() == {"from": "2026-11-01", "to": "2026-11-19"}


@pytest.mark.parametrize(
    "query",
    [
        {"from": "2026-11-01"},
        {"from": "01.11.2026", "to": "2026-11-19"},
        {"from": "2026-11-19", "to": "2026-11-01"},
        {"from": "2025-01-01", "to": "2026-11-19"},
    ],
)
def test_bad_custom_period(query):
    with pytest.raises(PeriodError):
        parse_period(query)


def test_longest_period_is_allowed():
    period = parse_period({"from": "2025-11-19", "to": "2026-11-19"})

    assert period.days == MAX_DAYS


def test_previous_period_has_the_same_length_and_ends_the_day_before():
    previous = Period(date(2026, 11, 1), date(2026, 11, 19)).previous

    assert previous == Period(date(2026, 10, 13), date(2026, 10, 31))


def test_compare_growth():
    assert compare(150, 100) == {
        "value": 150,
        "previous": 100,
        "direction": "up",
        "percent": Decimal("50.0"),
    }


def test_compare_fall_and_same():
    assert compare(Decimal("75"), Decimal("100"))["percent"] == Decimal("-25.0")
    assert compare(Decimal("75"), Decimal("100"))["direction"] == "down"
    assert compare(5, 5)["direction"] == "same"


def test_compare_with_nothing_before_has_no_percent():
    result = compare(10, 0)

    assert result["direction"] == "up"
    assert result["percent"] is None
    assert compare(None, None)["direction"] == "same"

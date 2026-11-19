"""The numbers of the reports (reports/queries.py) over the daily totals."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from reports import queries
from reports.aggregation import rebuild_days
from reports.periods import Period
from sales.models import Order, OrderLine
from tests.factories import BookFactory, CategoryFactory, OrderFactory, OrderLineFactory

pytestmark = pytest.mark.django_db

# Monday 2026-11-16 .. Thursday 2026-11-19
PERIOD = Period(date(2026, 11, 16), date(2026, 11, 19))


def noon(day):
    """12:00 in Kyiv of a day of November (UTC+2)."""
    return datetime(day.year, day.month, day.day, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def sales():
    """Three days with orders: 16th, 18th (two orders, one cancelled), 19th."""
    fiction, history = CategoryFactory(name="Fiction"), CategoryFactory(name="History")
    novel = BookFactory(title="Novel")
    novel.categories.set([fiction, history])
    guide = BookFactory(title="Guide")

    def order(day, book, *, format_type=OrderLine.FormatType.PAPER, amount="700", **fields):
        created = OrderFactory(
            created_at=noon(day),
            total=Decimal(amount),
            customer_key=fields.pop("key", "a" * 64),
            **fields,
        )
        OrderLineFactory(
            order=created, book=book, format_type=format_type, amount_uah=Decimal(amount)
        )
        return created

    order(date(2026, 11, 16), novel, payment_status=Order.PaymentStatus.PAID)
    order(
        date(2026, 11, 18),
        guide,
        format_type=OrderLine.FormatType.EBOOK,
        amount="300",
        key="b" * 64,
    )
    order(date(2026, 11, 18), novel, status=Order.Status.CANCELLED, key="c" * 64)
    order(date(2026, 11, 19), novel, amount="1000")
    rebuild_days(PERIOD.first + timedelta(days=offset) for offset in range(PERIOD.days))
    return {"novel": novel, "guide": guide}


def test_summary(sales):
    summary = queries.summary(PERIOD)

    assert summary["orders"] == 4
    assert summary["cancelled_orders"] == 1
    assert summary["revenue_uah"] == Decimal("2000")
    assert summary["average_order_uah"] == Decimal("666.67")
    assert summary["paid_share"] == Decimal("25.0")
    assert summary["cancelled_share"] == Decimal("25.0")


def test_summary_of_an_empty_period():
    summary = queries.summary(PERIOD)

    assert summary["orders"] == 0
    assert summary["average_order_uah"] == 0
    assert summary["paid_share"] == 0


def test_sales_by_day_fills_the_days_without_orders(sales):
    rows = queries.sales_by(PERIOD, "day")

    assert [row["day"] for row in rows] == [date(2026, 11, 16 + offset) for offset in range(4)]
    assert rows[1]["orders"] == 0
    assert rows[2]["orders"] == 2


@pytest.mark.parametrize(
    "group, first_day", [("week", date(2026, 11, 16)), ("month", date(2026, 11, 1))]
)
def test_sales_by_week_and_month(sales, group, first_day):
    rows = queries.sales_by(PERIOD, group)

    assert len(rows) == 1
    assert rows[0]["day"] == first_day
    assert rows[0]["orders"] == 4
    assert rows[0]["revenue_uah"] == Decimal("2000")


def test_books_best_first(sales):
    rows = queries.books(PERIOD)

    assert [row["title"] for row in rows] == ["Novel", "Guide"]
    # The cancelled order of the novel is not counted
    assert rows[0]["revenue_uah"] == Decimal("1700")
    assert rows[0]["quantity"] == 4
    assert queries.top_books(PERIOD, limit=1) == rows[:1]


def test_one_book(sales):
    novel = sales["novel"]

    days = queries.book_by_day(novel, PERIOD)
    formats = queries.book_formats(novel, PERIOD)

    assert len(days) == 4
    assert days[0]["revenue_uah"] == Decimal("700")
    assert days[1]["revenue_uah"] == 0
    assert formats == [{"format_type": "paper", "quantity": 4, "revenue_uah": Decimal("1700")}]


def test_formats_with_shares(sales):
    rows = {row["format_type"]: row for row in queries.formats(PERIOD)}

    assert rows["paper"]["revenue_share"] == Decimal("85.0")
    assert rows["ebook"]["revenue_share"] == Decimal("15.0")


def test_categories_count_a_book_in_each_of_its_categories(sales):
    rows = {row["name"]: row for row in queries.categories(PERIOD)}

    assert rows["Fiction"]["revenue_uah"] == Decimal("1700")
    assert rows["History"]["revenue_uah"] == Decimal("1700")
    # The guide has no category
    assert rows[None]["revenue_uah"] == Decimal("300")


def test_customers_by_day(sales):
    rows = {row["day"]: row for row in queries.customers(PERIOD)}

    assert rows[date(2026, 11, 16)]["new_customers"] == 1
    # The customer of the 16th orders again on the 19th
    assert rows[date(2026, 11, 19)]["returning_customers"] == 1
    assert rows[date(2026, 11, 19)]["returning_share"] == Decimal("100.0")


def test_cancelled_orders(sales):
    OrderFactory(
        status=Order.Status.CANCELLED,
        created_at=noon(date(2026, 11, 17)),
        cancelled_at=noon(date(2026, 11, 17)) + timedelta(hours=3),
    )
    # Outside the period
    OrderFactory(status=Order.Status.CANCELLED, created_at=noon(date(2026, 11, 10)))

    rows = queries.cancelled_orders(PERIOD)

    assert len(rows) == 2
    assert rows[0]["hours_to_cancel"] is None
    assert rows[1]["hours_to_cancel"] == Decimal("3.0")
    assert rows[0]["items"] == 2

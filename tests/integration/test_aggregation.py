"""Facts -> daily totals (reports/aggregation.py), the marks of changed days,
the periodic tasks and the command rebuild_reports."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import StringIO
from unittest import mock

import pytest
from django.core.management import CommandError, call_command

from events.contract import validate_event
from events.processing import process_event
from reports import tasks
from reports.aggregation import claim_dirty_days, mark_dirty, rebuild_day, rebuild_days
from reports.cache import cached_answer, current_version
from reports.models import DailyBookSales, DailySales, DirtyDay
from sales.models import Order, OrderLine
from tests.events_data import make_event
from tests.factories import BookFactory, OrderFactory, OrderLineFactory

pytestmark = pytest.mark.django_db

DAY = date(2026, 11, 18)
# 12:00 in Kyiv on DAY
NOON = datetime(2026, 11, 18, 10, 0, tzinfo=timezone.utc)


def order_with_line(**order_fields):
    """An order of DAY with one line: 2 paper copies x 350 = 700 UAH."""
    order = OrderFactory(**order_fields)
    OrderLineFactory(order=order, amount_uah=order.total_uah)
    return order


def test_day_totals():
    paid = order_with_line(payment_status=Order.PaymentStatus.PAID)
    order_with_line()
    order_with_line(status=Order.Status.CANCELLED)

    daily = rebuild_day(DAY)

    assert daily.orders == 3
    assert daily.paid_orders == 1
    assert daily.cancelled_orders == 1
    # The cancelled order is not revenue
    assert daily.revenue_uah == Decimal("1400.00")
    assert daily.paid_revenue_uah == paid.total_uah
    assert daily.items_sold == 4
    assert daily.average_order_uah == Decimal("700.00")


def test_order_after_kyiv_midnight_belongs_to_the_next_day():
    # 22:30 UTC on the 18th = 00:30 in Kyiv on the 19th
    order_with_line(created_at=datetime(2026, 11, 18, 22, 30, tzinfo=timezone.utc))

    assert rebuild_day(DAY) is None
    assert rebuild_day(DAY + timedelta(days=1)).orders == 1


def test_book_rows_group_by_book_and_format():
    book = BookFactory()
    order = OrderFactory()
    OrderLineFactory(order=order, book=book, quantity=1, amount_uah=Decimal("100"))
    OrderLineFactory(order=OrderFactory(), book=book, quantity=2, amount_uah=Decimal("200"))
    OrderLineFactory(
        order=order,
        book=book,
        format_type=OrderLine.FormatType.EBOOK,
        quantity=1,
        amount_uah=Decimal("50"),
    )
    # Lines of a cancelled order are not sales
    OrderLineFactory(order=OrderFactory(status=Order.Status.CANCELLED), book=book)

    rebuild_day(DAY)

    rows = {row.format_type: row for row in DailyBookSales.objects.filter(book=book)}
    assert rows["paper"].quantity == 3
    assert rows["paper"].revenue_uah == Decimal("300")
    assert rows["ebook"].quantity == 1


def test_new_and_returning_customers():
    OrderFactory(customer_key="a" * 64, created_at=NOON - timedelta(days=3))
    order_with_line(customer_key="a" * 64)
    order_with_line(customer_key="b" * 64)
    # The second order of a new customer on the same day: still one customer
    order_with_line(customer_key="b" * 64)
    # Only a cancelled order before: nothing was bought, the customer is new
    OrderFactory(
        customer_key="c" * 64,
        status=Order.Status.CANCELLED,
        created_at=NOON - timedelta(days=1),
    )
    order_with_line(customer_key="c" * 64)

    daily = rebuild_day(DAY)

    assert daily.new_customers == 2
    assert daily.returning_customers == 1


def test_rebuild_twice_gives_the_same_rows():
    order_with_line()

    rebuild_day(DAY)
    rebuild_day(DAY)

    assert DailySales.objects.get(day=DAY).orders == 1
    assert DailyBookSales.objects.filter(day=DAY).count() == 1


def test_day_without_orders_loses_its_rows():
    order = order_with_line()
    rebuild_day(DAY)
    order.delete()

    assert rebuild_day(DAY) is None
    assert not DailySales.objects.exists()
    assert not DailyBookSales.objects.exists()


def test_only_cancelled_orders_give_zero_average():
    order_with_line(status=Order.Status.CANCELLED)

    daily = rebuild_day(DAY)

    assert daily.revenue_uah == 0
    assert daily.average_order_uah == 0


def test_rebuild_invalidates_the_cached_answers():
    version = current_version()
    cached_answer("summary", {"day": DAY}, lambda: "old")

    rebuild_days([DAY])

    assert current_version() == version + 1
    # The same parameters miss the cache now and compute again
    assert cached_answer("summary", {"day": DAY}, lambda: "new") == "new"


def test_cached_answer_is_computed_once():
    compute = mock.Mock(return_value={"orders": 1})

    cached_answer("summary", {"from": DAY}, compute)
    cached_answer("summary", {"from": DAY}, compute)

    compute.assert_called_once()


# --- Marks of the changed days ---------------------------------------------


def test_event_marks_the_day_of_its_order():
    process_event(validate_event(make_event()))

    assert list(DirtyDay.objects.values_list("day", flat=True)) == [DAY]


def test_late_event_marks_the_day_the_order_was_created():
    # The order of the 18th is cancelled two days later: the 18th is marked
    process_event(
        validate_event(make_event("order.cancelled", minutes=2 * 24 * 60, status="cancelled"))
    )

    assert list(DirtyDay.objects.values_list("day", flat=True)) == [DAY]


def test_claim_takes_the_marks_away():
    mark_dirty(NOON)
    mark_dirty(NOON + timedelta(hours=1))

    assert claim_dirty_days() == [DAY]
    assert claim_dirty_days() == []


# --- Periodic tasks ----------------------------------------------------------


def test_refresh_reports_rebuilds_marked_days_and_today():
    order_with_line()
    mark_dirty(NOON)
    today = date(2026, 11, 20)

    with mock.patch.object(tasks, "today", return_value=today):
        result = tasks.refresh_reports.delay().get()

    assert result == [str(DAY), str(today)]
    assert DailySales.objects.get(day=DAY).orders == 1
    assert not DirtyDay.objects.exists()


def test_failed_refresh_marks_the_days_again():
    mark_dirty(NOON)

    with mock.patch.object(tasks, "rebuild_days", side_effect=RuntimeError("database down")):
        with pytest.raises(RuntimeError):
            tasks.refresh_reports.delay()

    assert list(DirtyDay.objects.values_list("day", flat=True)) == [DAY]


def test_close_yesterday():
    order_with_line()

    with mock.patch.object(tasks, "today", return_value=DAY + timedelta(days=1)):
        result = tasks.close_yesterday.delay().get()

    assert result == str(DAY)
    assert DailySales.objects.filter(day=DAY).exists()


# --- Command rebuild_reports -------------------------------------------------


def test_command_rebuilds_every_day_with_orders():
    order_with_line()
    order_with_line(created_at=NOON + timedelta(days=2))
    output = StringIO()

    call_command("rebuild_reports", stdout=output)

    assert "3 day(s)" in output.getvalue()
    assert DailySales.objects.count() == 2


def test_command_with_a_period():
    order_with_line()
    output = StringIO()

    call_command("rebuild_reports", "--from", "2026-11-17", "--to", "2026-11-18", stdout=output)

    assert "2 day(s)" in output.getvalue()


def test_command_without_orders():
    output = StringIO()

    call_command("rebuild_reports", stdout=output)

    assert "No orders yet" in output.getvalue()


def test_command_rejects_a_reversed_period():
    with pytest.raises(CommandError):
        call_command("rebuild_reports", "--from", "2026-11-19", "--to", "2026-11-18")

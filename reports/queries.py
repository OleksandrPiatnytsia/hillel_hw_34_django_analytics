"""The numbers of every report, read from the daily totals.

Each function takes a Period and returns plain data (dicts, lists,
Decimal): the same data goes to the web pages, to the CSV / XLSX exports
(stage 4.3) and to the REST API (stage 4.4), and can be kept in the cache
(reports/cache.py). No HTML, no translations here.

They read DailySales / DailyBookSales (one row per day, or per day + book +
format), never the orders themselves, except the list of cancelled orders.
"""

from decimal import Decimal

from django.db.models import Count, F, Sum
from django.db.models.functions import TruncMonth, TruncWeek

from sales.models import Order

from .days import day_bounds, days_between
from .models import DailyBookSales, DailySales

ZERO = Decimal("0")
CENT = Decimal("0.01")

SUMMED_FIELDS = (
    "orders",
    "paid_orders",
    "cancelled_orders",
    "revenue_uah",
    "paid_revenue_uah",
    "items_sold",
    "new_customers",
    "returning_customers",
)


def share(part, whole):
    """part of whole in percent, 0 for an empty whole."""
    if not whole:
        return ZERO
    return (Decimal(part) * 100 / Decimal(whole)).quantize(Decimal("0.1"))


def average(total, count):
    if not count:
        return ZERO
    return (Decimal(total) / count).quantize(CENT)


def with_derived(row):
    """Add the numbers computed from the sums: average order and the shares."""
    active = row["orders"] - row["cancelled_orders"]
    row["average_order_uah"] = average(row["revenue_uah"], active)
    row["paid_share"] = share(row["paid_orders"], row["orders"])
    row["cancelled_share"] = share(row["cancelled_orders"], row["orders"])
    return row


def daily_rows(period):
    return DailySales.objects.filter(day__range=(period.first, period.last))


def book_rows(period):
    return DailyBookSales.objects.filter(day__range=(period.first, period.last))


def summary(period):
    """The totals of the whole period: the KPI tiles."""
    sums = daily_rows(period).aggregate(**{field: Sum(field) for field in SUMMED_FIELDS})
    row = {field: sums[field] or 0 for field in SUMMED_FIELDS}
    return with_derived(row)


def empty_day(day):
    return with_derived({"day": day, **{field: 0 for field in SUMMED_FIELDS}})


def sales_by_day(period):
    """Every day of the period, zeros for a day without orders (a chart
    without gaps)."""
    stored = {row["day"]: row for row in daily_rows(period).values("day", *SUMMED_FIELDS)}
    return [
        with_derived(stored[day]) if day in stored else empty_day(day)
        for day in days_between(period.first, period.last)
    ]


TRUNCATE = {"week": TruncWeek, "month": TruncMonth}


def sales_by(period, group="day"):
    """Sales by day, week (from Monday) or month; the row key is "day" = the
    first day of the group. A week or a month cut by the period boundary
    has only the days inside the period."""
    if group == "day":
        return sales_by_day(period)
    rows = (
        daily_rows(period)
        .annotate(start=TRUNCATE[group]("day"))
        .values("start")
        .annotate(**{field: Sum(field) for field in SUMMED_FIELDS})
        .order_by("start")
    )
    return [with_derived({"day": row.pop("start"), **row}) for row in rows]


def books(period):
    """Every book sold in the period: copies and revenue, best first."""
    rows = (
        book_rows(period)
        .values(
            "book_id",
            # The id in the bookstore: the REST API gives it, so the bookstore
            # can link the row to its own book page
            source_id=F("book__source_id"),
            title=F("book__title"),
            author=F("book__author"),
        )
        .annotate(quantity=Sum("quantity"), revenue_uah=Sum("revenue_uah"))
        .order_by("-revenue_uah", "title")
    )
    return list(rows)


def top_books(period, limit=10):
    return books(period)[:limit]


def book_formats(book, period):
    """One book: copies and revenue per format."""
    return list(
        book_rows(period)
        .filter(book=book)
        .values("format_type")
        .annotate(quantity=Sum("quantity"), revenue_uah=Sum("revenue_uah"))
        .order_by("-revenue_uah")
    )


def book_by_day(book, period):
    """One book: copies and revenue of every day of the period."""
    stored = {
        row["day"]: row
        for row in book_rows(period)
        .filter(book=book)
        .values("day")
        .annotate(quantity=Sum("quantity"), revenue_uah=Sum("revenue_uah"))
    }
    return [
        stored.get(day, {"day": day, "quantity": 0, "revenue_uah": ZERO})
        for day in days_between(period.first, period.last)
    ]


def formats(period):
    """Paper / e-book / audio: copies, revenue and the share of revenue."""
    rows = list(
        book_rows(period)
        .values("format_type")
        .annotate(quantity=Sum("quantity"), revenue_uah=Sum("revenue_uah"))
        .order_by("-revenue_uah")
    )
    total = sum(row["revenue_uah"] for row in rows)
    for row in rows:
        row["revenue_share"] = share(row["revenue_uah"], total)
    return rows


def categories(period):
    """Copies and revenue per category.

    A book with two categories counts in both: the sum of this report is
    larger than the total revenue (the page says so under the table). A
    book without categories is in a row with an empty name.
    """
    rows = (
        book_rows(period)
        .values(category_id=F("book__categories__id"), name=F("book__categories__name"))
        .annotate(
            quantity=Sum("quantity"),
            revenue_uah=Sum("revenue_uah"),
            books=Count("book", distinct=True),
        )
        .order_by("-revenue_uah")
    )
    return list(rows)


def customers(period):
    """New and returning customers of every day."""
    return [
        {
            "day": row["day"],
            "new_customers": row["new_customers"],
            "returning_customers": row["returning_customers"],
            "customers": row["new_customers"] + row["returning_customers"],
            "returning_share": share(
                row["returning_customers"], row["new_customers"] + row["returning_customers"]
            ),
        }
        for row in sales_by_day(period)
    ]


def cancelled_orders(period):
    """The cancelled orders created in the period (the table of the report).

    From the orders themselves: the daily totals don't keep single orders.
    """
    start, _end = day_bounds(period.first)
    _start, end = day_bounds(period.last)
    rows = (
        Order.objects.filter(
            status=Order.Status.CANCELLED, created_at__gte=start, created_at__lt=end
        )
        .annotate(items=Sum("lines__quantity"))
        .values(
            "source_id",
            "created_at",
            "cancelled_at",
            "payment_status",
            "total_uah",
            "items",
        )
        .order_by("-created_at")
    )
    rows = list(rows)
    for row in rows:
        # Hours from the order to its cancellation: how fast customers change their mind
        if row["cancelled_at"]:
            seconds = (row["cancelled_at"] - row["created_at"]).total_seconds()
            row["hours_to_cancel"] = Decimal(seconds / 3600).quantize(Decimal("0.1"))
        else:
            row["hours_to_cancel"] = None
    return rows


def has_any_data():
    """Has a single day been computed yet (the empty state of the dashboard)."""
    return DailySales.objects.exists()

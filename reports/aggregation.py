"""Facts -> totals: compute DailySales and DailyBookSales of a day.

    sales.Order / OrderLine of one Kyiv day
        --sums in PostgreSQL-->  DailySales (1 row)
                                 DailyBookSales (1 row per book + format)

rebuild_day() throws away what was computed for the day and computes it
again from the facts. No "add one order to the totals": a repeated run
(Celery retries a task after a crash, acks_late), a late event or a
backfill can never count an order twice, the result is always the same.
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum

from sales.models import Order, OrderLine

from .cache import invalidate_reports
from .days import day_bounds, local_day
from .models import DailyBookSales, DailySales, DirtyDay

logger = logging.getLogger(__name__)  # "reports.aggregation"

CENT = Decimal("0.01")
ZERO = Decimal("0")


def orders_of_day(day):
    start, end = day_bounds(day)
    return Order.objects.filter(created_at__gte=start, created_at__lt=end)


def count_customers(active_orders, start):
    """(new, returning) customers among the orders that are not cancelled.

    New = no order of this customer before the day. A cancelled order
    doesn't make a customer: nothing was bought.
    Note: when an older order arrives later (the backfill of stage 5), the
    following days of that customer must be recalculated too; the command
    rebuild_reports does it for a whole period.
    """
    keys = set(active_orders.values_list("customer_key", flat=True).distinct())
    returning = set(
        Order.objects.exclude(status=Order.Status.CANCELLED)
        .filter(created_at__lt=start, customer_key__in=keys)
        .values_list("customer_key", flat=True)
        .distinct()
    )
    return len(keys - returning), len(keys & returning)


@transaction.atomic
def rebuild_day(day):
    """Compute the totals of one day again. Returns its DailySales or None.

    A day without orders has no rows at all (the pages show zeros for the
    days that are missing). In one transaction: a report never sees the
    day half rebuilt.
    """
    orders = orders_of_day(day)
    active = orders.exclude(status=Order.Status.CANCELLED)
    paid = Q(payment_status=Order.PaymentStatus.PAID)

    totals = orders.aggregate(
        orders=Count("id"),
        paid_orders=Count("id", filter=paid),
        cancelled_orders=Count("id", filter=Q(status=Order.Status.CANCELLED)),
        revenue_uah=Sum("total_uah", filter=~Q(status=Order.Status.CANCELLED)),
        paid_revenue_uah=Sum("total_uah", filter=paid & ~Q(status=Order.Status.CANCELLED)),
    )
    DailyBookSales.objects.filter(day=day).delete()
    if not totals["orders"]:
        DailySales.objects.filter(day=day).delete()
        return None

    active_count = totals["orders"] - totals["cancelled_orders"]
    revenue = totals["revenue_uah"] or ZERO
    lines = OrderLine.objects.filter(order__in=active)
    start, _end = day_bounds(day)
    new_customers, returning_customers = count_customers(active, start)

    daily, _created = DailySales.objects.update_or_create(
        day=day,
        defaults={
            "orders": totals["orders"],
            "paid_orders": totals["paid_orders"],
            "cancelled_orders": totals["cancelled_orders"],
            "revenue_uah": revenue,
            "paid_revenue_uah": totals["paid_revenue_uah"] or ZERO,
            "items_sold": lines.aggregate(total=Sum("quantity"))["total"] or 0,
            "average_order_uah": (revenue / active_count).quantize(CENT) if active_count else ZERO,
            "new_customers": new_customers,
            "returning_customers": returning_customers,
        },
    )

    # One row per book + format: GROUP BY book_id, format_type
    per_book = lines.values("book_id", "format_type").annotate(
        quantity=Sum("quantity"), revenue_uah=Sum("amount_uah")
    )
    DailyBookSales.objects.bulk_create(
        DailyBookSales(
            day=day,
            book_id=row["book_id"],
            format_type=row["format_type"],
            quantity=row["quantity"],
            revenue_uah=row["revenue_uah"],
        )
        for row in per_book
    )
    return daily


def rebuild_days(days):
    """Rebuild several days, then drop the cached report answers once."""
    days = sorted(set(days))
    for day in days:
        rebuild_day(day)
    if days:
        invalidate_reports()
        logger.info("Reports recalculated: %d day(s), %s .. %s", len(days), days[0], days[-1])
    return days


def mark_dirty(moment):
    """Remember that the day of this moment must be recalculated.

    Called inside the transaction of the event (events/processing.py).
    update_or_create on a unique day: many events of one day = one mark.
    """
    DirtyDay.objects.update_or_create(day=local_day(moment))


def claim_dirty_days():
    """Take all the marks away and return their days.

    select_for_update waits for an event transaction that is changing a
    mark right now, so its order is already committed when the day is
    recalculated. A mark added after this moment stays for the next run.
    """
    with transaction.atomic():
        days = list(DirtyDay.objects.select_for_update().values_list("day", flat=True))
        DirtyDay.objects.filter(day__in=days).delete()
    return days


def mark_days(days):
    """Put the marks back (the recalculation failed: try again next run)."""
    for day in days:
        DirtyDay.objects.update_or_create(day=day)

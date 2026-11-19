"""Recalculate the daily totals of a period from the orders.

    python manage.py rebuild_reports                              every day with orders
    python manage.py rebuild_reports --from 2026-11-01 --to 2026-11-19

For the first start on a database that already has orders, after the
backfill of old orders (stage 5) and after a fix of the aggregation code.
Safe to run any number of times: every day is computed from scratch.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max, Min

from reports.aggregation import rebuild_days
from reports.days import days_between, local_day, parse_day
from sales.models import Order


class Command(BaseCommand):
    help = "Recalculate the daily report totals of a period (default: every day with orders)."

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="first", type=parse_day, help="YYYY-MM-DD")
        parser.add_argument("--to", dest="last", type=parse_day, help="YYYY-MM-DD")

    def handle(self, *args, first=None, last=None, **options):
        if first is None or last is None:
            bounds = Order.objects.aggregate(first=Min("created_at"), last=Max("created_at"))
            if bounds["first"] is None:
                self.stdout.write("No orders yet, nothing to recalculate.")
                return
            first = first or local_day(bounds["first"])
            last = last or local_day(bounds["last"])
        if first > last:
            raise CommandError("--from must not be later than --to")

        days = rebuild_days(days_between(first, last))
        self.stdout.write(
            self.style.SUCCESS(f"Recalculated {len(days)} day(s): {days[0]} .. {days[-1]}")
        )

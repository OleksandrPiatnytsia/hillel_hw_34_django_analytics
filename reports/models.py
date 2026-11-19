"""Ready totals per day: what the report pages and the API read.

The facts (sales.Order / OrderLine) are the truth; these tables are a
summary computed from them by reports/aggregation.py. Any row here can be
deleted and computed again, so a recalculation is always safe to repeat.

Why store totals at all: a report for 90 days reads 90 rows instead of
summing thousands of orders and lines on every page view.

The rules of a day (approved 2026-11-19):
- a day is a calendar day in Kyiv (reports/days.py);
- an order belongs to the day it was CREATED: its payment and its
  cancellation are counted in that day too, even when they happen later
  (then that old day is recalculated, see DirtyDay);
- revenue = orders that are not cancelled; the paid part is a column of its own.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from catalog.models import Book
from sales.models import OrderLine


class DailySales(models.Model):
    day = models.DateField(_("day"), unique=True)
    # All orders created this day, cancelled ones included
    orders = models.PositiveIntegerField(_("orders"), default=0)
    paid_orders = models.PositiveIntegerField(_("paid orders"), default=0)
    cancelled_orders = models.PositiveIntegerField(_("cancelled orders"), default=0)
    # Orders that are not cancelled
    revenue_uah = models.DecimalField(_("revenue, UAH"), max_digits=14, decimal_places=2, default=0)
    # Of them, the paid ones
    paid_revenue_uah = models.DecimalField(
        _("paid revenue, UAH"), max_digits=14, decimal_places=2, default=0
    )
    # Copies in the orders that are not cancelled
    items_sold = models.PositiveIntegerField(_("items sold"), default=0)
    # revenue_uah / orders that are not cancelled
    average_order_uah = models.DecimalField(
        _("average order, UAH"), max_digits=12, decimal_places=2, default=0
    )
    # Customers (customer_key) whose very first order is of this day
    new_customers = models.PositiveIntegerField(_("new customers"), default=0)
    # Customers of this day who had ordered before
    returning_customers = models.PositiveIntegerField(_("returning customers"), default=0)
    # When this row was last computed
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("daily sales")
        verbose_name_plural = _("daily sales")
        ordering = ["-day"]

    def __str__(self):
        return str(self.day)


class DailyBookSales(models.Model):
    """Copies and revenue of one book in one format on one day.

    Only orders that are not cancelled. The reports of books, formats and
    categories are sums of these rows.
    """

    day = models.DateField(_("day"), db_index=True)
    # PROTECT, as in sales.OrderLine: a book with sales stays
    book = models.ForeignKey(
        Book, on_delete=models.PROTECT, related_name="daily_sales", verbose_name=_("book")
    )
    format_type = models.CharField(_("format"), max_length=10, choices=OrderLine.FormatType.choices)
    quantity = models.PositiveIntegerField(_("quantity"), default=0)
    revenue_uah = models.DecimalField(_("revenue, UAH"), max_digits=14, decimal_places=2, default=0)

    class Meta:
        verbose_name = _("daily book sales")
        verbose_name_plural = _("daily book sales")
        ordering = ["-day", "-revenue_uah"]
        constraints = [
            models.UniqueConstraint(
                fields=["day", "book", "format_type"], name="unique_daily_book_format"
            )
        ]

    def __str__(self):
        return f"{self.day} {self.book} ({self.format_type})"


class DirtyDay(models.Model):
    """A day whose orders changed after its totals were computed.

    The consumer marks the day of an order in the SAME transaction as the
    change of the order (events/processing.py): the mark exists exactly
    when the change does, never before the commit and never lost after it.
    The periodic task (reports/tasks.py) takes the marks, recalculates those
    days and so catches a late payment, a cancellation of a week-old order
    or a backfill of old orders, not only today.
    """

    day = models.DateField(_("day"), unique=True)
    marked_at = models.DateTimeField(_("marked at"), auto_now=True)

    class Meta:
        verbose_name = _("day to recalculate")
        verbose_name_plural = _("days to recalculate")
        ordering = ["day"]

    def __str__(self):
        return str(self.day)


class ReportExport(models.Model):
    """A CSV or XLSX file of a report, made in the background by Celery.

        report page --POST--> ReportExport(pending) --Celery--> running
            --> done (the file is in `content`) or failed (`error`)

    The file is stored in the database, not on a disk: on Railway the web
    service and the Celery worker are separate machines without a shared
    disk, and the database is what both of them see. The files are small
    (at most a year of days or a few thousand orders) and are deleted after
    EXPORTS_KEEP_DAYS by a nightly task, so the table doesn't grow.
    """

    class Format(models.TextChoices):
        CSV = "csv", "CSV"
        XLSX = "xlsx", "XLSX"

    class Status(models.TextChoices):
        PENDING = "pending", _("Waiting")
        RUNNING = "running", _("Running")
        DONE = "done", _("Ready")
        FAILED = "failed", _("Failed")

    # Only the author can download the file (reports/views.py)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="report_exports",
        verbose_name=_("user"),
    )
    # ReportBaseView.report_name: sales, books, book, formats, ...
    report = models.CharField(_("report"), max_length=30)
    # The real dates (from / to), the filters and the sort of the page
    params = models.JSONField(_("parameters"), default=dict)
    format = models.CharField(_("format"), max_length=4, choices=Format.choices)
    # The column names are written in the language of the page
    language = models.CharField(_("language"), max_length=10)
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.PENDING
    )
    filename = models.CharField(_("file name"), max_length=150, blank=True)
    content = models.BinaryField(_("file"), null=True, blank=True)
    size = models.PositiveIntegerField(_("size, bytes"), default=0)
    error = models.TextField(_("error"), blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(_("finished at"), null=True, blank=True)

    class Meta:
        verbose_name = _("report export")
        verbose_name_plural = _("report exports")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.report} {self.format} #{self.pk}"

    @property
    def is_finished(self):
        return self.status in (self.Status.DONE, self.Status.FAILED)

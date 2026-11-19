"""The dashboard and the report pages.

Every report page is the same machine with different numbers:

    AnalyticsAccessMixin   logged in + users.view_analytics (403 otherwise)
        ReportBaseView     the period from the URL, the comparison with the
                           previous period (KPI tiles), the chart, the table:
                           sorting, pages, the cache of the answers
            SalesReportView, BooksReportView, ... override only
            get_rows() (the numbers), columns (the table) and get_chart()

The numbers come from reports/queries.py through the cache of answers
(reports/cache.py): the same filters within one recalculation = one query.
"""

from dataclasses import dataclass
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, TemplateView

from catalog.models import Book
from events.models import Event, EventType
from sales.models import Order, OrderLine

from . import queries
from .cache import cached_answer
from .periods import DEFAULT_PRESET, PRESETS, PeriodError, compare, parse_period, preset_period


class AnalyticsAccessMixin(LoginRequiredMixin, PermissionRequiredMixin):
    """The access rule of every analytics page: logged in + users.view_analytics.

    An anonymous visitor goes to the login page (LoginRequiredMixin); a
    logged-in user without the permission gets 403 (raise_exception), not
    a login page again, which would look like a loop. The dashboard and the
    report pages inherit it instead of repeating it.
    """

    permission_required = "users.view_analytics"

    def handle_no_permission(self):
        # raise_exception only for logged-in users: anonymous ones still
        # get the redirect to the login page
        self.raise_exception = self.request.user.is_authenticated
        return super().handle_no_permission()


@dataclass(frozen=True)
class Column:
    """One column of a report table.

    kind tells the template how to show a value (reports/templatetags):
    text, int, money, percent, day, month, datetime, book, format,
    category, order, payment.
    """

    key: str
    label: str
    kind: str = "int"
    sortable: bool = True

    @property
    def numeric(self):
        """Numbers are aligned to the right, so the digits stand under each other."""
        return self.kind in ("int", "money", "percent", "decimal")


@dataclass(frozen=True)
class Tile:
    """A KPI tile: a value of the summary, compared with the previous period."""

    key: str
    label: str
    kind: str
    # The report the tile leads to
    url_name: str
    # False for the share of cancellations: its growth is bad news (red)
    good_when_up: bool = True


TILES = {
    tile.key: tile
    for tile in (
        Tile("revenue_uah", _("Revenue"), "money", "reports:sales"),
        Tile("orders", _("Orders"), "int", "reports:sales"),
        Tile("average_order_uah", _("Average order"), "money", "reports:sales"),
        Tile("items_sold", _("Copies sold"), "int", "reports:books"),
        Tile("paid_share", _("Paid"), "percent", "reports:sales"),
        Tile("cancelled_orders", _("Cancelled orders"), "int", "reports:cancellations", False),
        Tile("cancelled_share", _("Cancelled"), "percent", "reports:cancellations", False),
        Tile("new_customers", _("New customers"), "int", "reports:customers"),
        Tile("returning_customers", _("Returning customers"), "int", "reports:customers"),
    )
}


def chart(kind, labels, datasets, **options):
    """The data of one Chart.js chart, for json_script.

    datasets: [(label, values), ...]. Decimal -> float: JSON has no Decimal,
    and a chart needs no cents precision.
    """
    return {
        "type": kind,
        "labels": [str(label) for label in labels],
        "datasets": [
            {"label": str(label), "data": [float(value or 0) for value in values]}
            for label, values in datasets
        ],
        "options": options,
    }


def tile_item(tile, current, previous):
    """A tile with its comparison and the colour of the arrow: green when
    the change is good news, red when bad (more cancellations = red)."""
    item = {"tile": tile, **compare(current, previous)}
    good = {"up": tile.good_when_up, "down": not tile.good_when_up}.get(item["direction"])
    item["tone"] = "secondary" if good is None else ("success" if good else "danger")
    return item


def format_name(value):
    return str(OrderLine.FormatType(value).label) if value else ""


class ReportBaseView(AnalyticsAccessMixin, TemplateView):
    template_name = "reports/report.html"
    # The key of the cached answers (and of the exports at stage 4.3)
    report_name = ""
    title = ""
    description = ""
    columns = []
    # "-revenue_uah" = by revenue, the largest first; "" = as get_rows returns
    default_sort = ""
    paginate_by = 25
    # The KPI tiles above the chart (keys of TILES)
    tile_keys = ("revenue_uah", "orders", "average_order_uah")
    # A note under the table
    note = ""

    def get(self, request, *args, **kwargs):
        try:
            self.period = parse_period(request.GET)
        except PeriodError as error:
            # A broken bookmark or a typo in a date: the default period and
            # a message instead of an error page
            messages.error(request, str(error))
            self.period = preset_period(DEFAULT_PRESET)
        return super().get(request, *args, **kwargs)

    # --- what a report overrides ---------------------------------------------

    def get_rows(self):
        """The rows of the table: a list of dicts (reports/queries.py)."""
        return []

    def get_chart(self, rows):
        """The main chart (see chart()), or None."""
        return None

    def get_charts(self, rows):
        main = self.get_chart(rows)
        return {"main": main} if main else {}

    def get_extra_params(self):
        """Filters of a report besides the period (the group of the sales)."""
        return {}

    def get_columns(self):
        return self.columns

    # --- the common part -----------------------------------------------------

    def cached(self, name, compute, period=None, **params):
        """compute() through the cache of answers. The key holds the real
        dates, not "period=30": the last 30 days are other days tomorrow."""
        period = period or self.period
        key_params = {"first": period.first, "last": period.last, **params}
        return cached_answer(name, key_params, compute)

    def get_summary(self, period):
        return self.cached("summary", lambda: queries.summary(period), period=period)

    def get_tiles(self):
        current = self.get_summary(self.period)
        previous = self.get_summary(self.period.previous)
        return [tile_item(TILES[key], current[key], previous[key]) for key in self.tile_keys]

    def get_sort(self):
        allowed = {column.key for column in self.get_columns() if column.sortable}
        sort = self.request.GET.get("sort", self.default_sort)
        return sort if sort.lstrip("-") in allowed else self.default_sort

    def sort_rows(self, rows, sort):
        if not sort:
            return rows
        key = sort.lstrip("-")
        # (is empty, value): empty values (no category, no date) go last
        # when ascending, and None is never compared with a number
        return sorted(
            rows,
            key=lambda row: (row.get(key) is None, row.get(key) or 0),
            reverse=sort.startswith("-"),
        )

    def get_headers(self, sort):
        """Every column with the sort value of its link: a click on the
        sorted column turns the order around."""
        headers = []
        for column in self.get_columns():
            state = ""
            if sort.lstrip("-") == column.key:
                state = "desc" if sort.startswith("-") else "asc"
            # Numbers: the largest first on the first click; text: A to Z
            first_order = "" if column.kind in ("text", "book", "category") else "-"
            next_sort = {"desc": column.key, "asc": f"-{column.key}"}.get(
                state, f"{first_order}{column.key}"
            )
            headers.append({"column": column, "state": state, "next_sort": next_sort})
        return headers

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows = self.cached(self.report_name, self.get_rows, **self.get_extra_params())
        sort = self.get_sort()
        # The print view (?print=1): every row on one page
        printing = bool(self.request.GET.get("print"))
        per_page = max(len(rows), 1) if printing else self.paginate_by
        page = Paginator(self.sort_rows(rows, sort), per_page).get_page(
            self.request.GET.get("page")
        )
        context.update(
            title=self.title,
            description=self.description,
            note=self.note,
            period=self.period,
            # The period as a query: the tiles lead to their reports with it
            period_query=urlencode(self.period.as_params()),
            presets=PRESETS,
            printing=printing,
            extra_params=self.get_extra_params(),
            tiles=self.get_tiles(),
            charts=self.get_charts(rows),
            headers=self.get_headers(sort),
            page_obj=page,
            rows=page.object_list,
            elided_pages=page.paginator.get_elided_page_range(page.number),
        )
        return context


class DashboardView(ReportBaseView):
    """The home page: all KPI tiles and four charts, each leading to its report."""

    template_name = "reports/dashboard.html"
    report_name = "dashboard"
    title = _("Dashboard")
    tile_keys = (
        "revenue_uah",
        "orders",
        "average_order_uah",
        "paid_share",
        "cancelled_share",
        "new_customers",
    )

    def get_charts(self, rows):
        period = self.period
        days = self.cached("sales:day", lambda: queries.sales_by(period, "day"))
        top = self.cached("top-books", lambda: queries.top_books(period))
        format_rows = self.cached("formats", lambda: queries.formats(period))
        category_rows = self.cached("categories", lambda: queries.categories(period))[:10]
        return {
            "revenue": chart(
                "line",
                [row["day"] for row in days],
                [(_("Revenue"), [r["revenue_uah"] for r in days])],
            ),
            "books": chart(
                "bar",
                [row["title"] for row in top],
                [(_("Revenue"), [row["revenue_uah"] for row in top])],
                indexAxis="y",
            ),
            "formats": chart(
                "doughnut",
                [format_name(row["format_type"]) for row in format_rows],
                [(_("Revenue"), [row["revenue_uah"] for row in format_rows])],
            ),
            "categories": chart(
                "bar",
                [row["name"] or _("No category") for row in category_rows],
                [(_("Revenue"), [row["revenue_uah"] for row in category_rows])],
            ),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["has_data"] = queries.has_any_data()
        return context


GROUPS = {
    "day": (_("Day"), "day"),
    "week": (_("Week (from Monday)"), "day"),
    "month": (_("Month"), "month"),
}


class SalesReportView(ReportBaseView):
    template_name = "reports/sales.html"
    report_name = "sales"
    title = _("Sales")
    description = _("Orders and revenue by day, week or month.")
    default_sort = "-day"
    tile_keys = ("revenue_uah", "orders", "average_order_uah", "paid_share")

    def get_group(self):
        group = self.request.GET.get("group", "day")
        return group if group in GROUPS else "day"

    def get_extra_params(self):
        return {"group": self.get_group()}

    def get_columns(self):
        label, kind = GROUPS[self.get_group()]
        return [
            Column("day", label, kind),
            Column("orders", _("Orders")),
            Column("paid_orders", _("Paid")),
            Column("cancelled_orders", _("Cancelled")),
            Column("revenue_uah", _("Revenue, UAH"), "money"),
            Column("paid_revenue_uah", _("Paid revenue, UAH"), "money"),
            Column("items_sold", _("Copies")),
            Column("average_order_uah", _("Average order, UAH"), "money"),
        ]

    def get_rows(self):
        return queries.sales_by(self.period, self.get_group())

    def get_chart(self, rows):
        return chart(
            "line",
            [row["day"] for row in rows],
            [
                (_("Revenue"), [row["revenue_uah"] for row in rows]),
                (_("Paid revenue"), [row["paid_revenue_uah"] for row in rows]),
            ],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["groups"] = [(key, label) for key, (label, _kind) in GROUPS.items()]
        context["group"] = self.get_group()
        return context


class BooksReportView(ReportBaseView):
    report_name = "books"
    title = _("Books")
    description = _("Every book sold in the period. Click a title for its own page.")
    default_sort = "-revenue_uah"
    tile_keys = ("revenue_uah", "items_sold")
    columns = [
        Column("title", _("Title"), "book"),
        Column("author", _("Author"), "text"),
        Column("quantity", _("Copies")),
        Column("revenue_uah", _("Revenue, UAH"), "money"),
    ]

    def get_rows(self):
        return queries.books(self.period)

    def get_chart(self, rows):
        top = rows[:10]
        return chart(
            "bar",
            [row["title"] for row in top],
            [(_("Revenue"), [row["revenue_uah"] for row in top])],
            indexAxis="y",
        )


class BookReportView(ReportBaseView):
    """One book: its sales by day and its formats."""

    template_name = "reports/book.html"
    report_name = "book"
    default_sort = "-day"
    columns = [
        Column("day", _("Day"), "day"),
        Column("quantity", _("Copies")),
        Column("revenue_uah", _("Revenue, UAH"), "money"),
    ]

    def dispatch(self, request, *args, **kwargs):
        self.book = get_object_or_404(Book, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    @property
    def title(self):
        return self.book.title

    def get_extra_params(self):
        return {"book": self.book.pk}

    def get_rows(self):
        return queries.book_by_day(self.book, self.period)

    def book_totals(self, period):
        rows = self.cached(
            "book", lambda: queries.book_by_day(self.book, period), period=period, book=self.book.pk
        )
        return {
            "quantity": sum(row["quantity"] for row in rows),
            "revenue_uah": sum(row["revenue_uah"] for row in rows),
        }

    def get_tiles(self):
        current = self.book_totals(self.period)
        previous = self.book_totals(self.period.previous)
        tiles = (
            Tile("revenue_uah", _("Revenue"), "money", "reports:books"),
            Tile("quantity", _("Copies sold"), "int", "reports:books"),
        )
        return [tile_item(tile, current[tile.key], previous[tile.key]) for tile in tiles]

    def get_format_rows(self):
        return self.cached(
            "book-formats", lambda: queries.book_formats(self.book, self.period), book=self.book.pk
        )

    def get_charts(self, rows):
        format_rows = self.get_format_rows()
        return {
            "main": chart(
                "line",
                [row["day"] for row in rows],
                [(_("Revenue"), [r["revenue_uah"] for r in rows])],
            ),
            "formats": chart(
                "doughnut",
                [format_name(row["format_type"]) for row in format_rows],
                [(_("Copies"), [row["quantity"] for row in format_rows])],
            ),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["book"] = self.book
        context["format_rows"] = self.get_format_rows()
        return context


class FormatsReportView(ReportBaseView):
    report_name = "formats"
    title = _("Formats")
    description = _("Paper books, e-books and audiobooks.")
    default_sort = "-revenue_uah"
    tile_keys = ("revenue_uah", "items_sold")
    columns = [
        Column("format_type", _("Format"), "format"),
        Column("quantity", _("Copies")),
        Column("revenue_uah", _("Revenue, UAH"), "money"),
        Column("revenue_share", _("Share of revenue"), "percent"),
    ]

    def get_rows(self):
        return queries.formats(self.period)

    def get_chart(self, rows):
        return chart(
            "doughnut",
            [format_name(row["format_type"]) for row in rows],
            [(_("Revenue"), [row["revenue_uah"] for row in rows])],
        )


class CategoriesReportView(ReportBaseView):
    report_name = "categories"
    title = _("Categories")
    description = _("Copies and revenue of the books of every category.")
    note = _(
        "A book with several categories is counted in each of them, so the sum "
        "of this table can be larger than the total revenue."
    )
    default_sort = "-revenue_uah"
    tile_keys = ("revenue_uah", "items_sold")
    columns = [
        Column("name", _("Category"), "category"),
        Column("books", _("Books")),
        Column("quantity", _("Copies")),
        Column("revenue_uah", _("Revenue, UAH"), "money"),
    ]

    def get_rows(self):
        return queries.categories(self.period)

    def get_chart(self, rows):
        top = rows[:15]
        return chart(
            "bar",
            [row["name"] or _("No category") for row in top],
            [(_("Revenue"), [row["revenue_uah"] for row in top])],
        )


class CustomersReportView(ReportBaseView):
    report_name = "customers"
    title = _("Customers")
    description = _(
        "New customers make their first order; returning ones have ordered before. "
        "No personal data: a customer is an anonymous key."
    )
    default_sort = "-day"
    tile_keys = ("new_customers", "returning_customers")
    columns = [
        Column("day", _("Day"), "day"),
        Column("new_customers", _("New customers")),
        Column("returning_customers", _("Returning customers")),
        Column("customers", _("Customers")),
        Column("returning_share", _("Returning share"), "percent"),
    ]

    def get_rows(self):
        return queries.customers(self.period)

    def get_chart(self, rows):
        return chart(
            "bar",
            [row["day"] for row in rows],
            [
                (_("New customers"), [row["new_customers"] for row in rows]),
                (_("Returning customers"), [row["returning_customers"] for row in rows]),
            ],
            scales={"x": {"stacked": True}, "y": {"stacked": True}},
        )


class CancellationsReportView(ReportBaseView):
    report_name = "cancellations"
    title = _("Cancellations")
    description = _("The share of cancelled orders by day and every cancelled order.")
    default_sort = "-created_at"
    tile_keys = ("orders", "cancelled_orders", "cancelled_share")
    columns = [
        Column("source_id", _("Order"), "order"),
        Column("created_at", _("Created"), "datetime"),
        Column("cancelled_at", _("Cancelled"), "datetime"),
        Column("payment_status", _("Payment"), "payment"),
        Column("items", _("Copies")),
        Column("total_uah", _("Total, UAH"), "money"),
        Column("hours_to_cancel", _("Hours to cancel"), "decimal"),
    ]

    def get_rows(self):
        return queries.cancelled_orders(self.period)

    def get_chart(self, rows):
        # The chart is by day, the table is by order: the days come from
        # the daily totals
        days = self.cached("sales:day", lambda: queries.sales_by(self.period, "day"))
        return chart(
            "line",
            [row["day"] for row in days],
            [(_("Cancelled, %"), [row["cancelled_share"] for row in days])],
        )


# --- Lists of single records ---------------------------------------------------


class OrderListView(AnalyticsAccessMixin, ListView):
    """The orders as the events described them, newest first."""

    template_name = "reports/orders.html"
    paginate_by = 25

    def get_queryset(self):
        orders = Order.objects.annotate(items=Sum("lines__quantity"), lines_count=Count("lines"))
        status = self.request.GET.get("status")
        if status in Order.Status.values:
            orders = orders.filter(status=status)
        payment = self.request.GET.get("payment")
        if payment in Order.PaymentStatus.values:
            orders = orders.filter(payment_status=payment)
        number = self.request.GET.get("number", "").strip()
        if number.isdigit():
            orders = orders.filter(source_id=int(number))
        return orders.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            statuses=Order.Status.choices,
            payments=Order.PaymentStatus.choices,
            elided_pages=context["paginator"].get_elided_page_range(context["page_obj"].number),
        )
        return context


class EventListView(AnalyticsAccessMixin, ListView):
    """The journal of the events: what came from the bookstore, what failed.

    For the administrators (events.view_event: superusers and whoever gets
    it in the admin), not for the analysts: an error text may quote a
    broken message.
    """

    permission_required = "events.view_event"
    template_name = "reports/events.html"
    paginate_by = 50

    def get_queryset(self):
        events = Event.objects.all()
        status = self.request.GET.get("status")
        if status in Event.Status.values:
            events = events.filter(status=status)
        event_type = self.request.GET.get("type")
        if event_type in EventType.values:
            events = events.filter(type=event_type)
        return events.order_by("-received_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            statuses=Event.Status.choices,
            types=EventType.choices,
            failed_count=Event.objects.filter(status=Event.Status.FAILED).count(),
            admin_url=reverse("admin:events_event_changelist"),
            elided_pages=context["paginator"].get_elided_page_range(context["page_obj"].number),
        )
        return context

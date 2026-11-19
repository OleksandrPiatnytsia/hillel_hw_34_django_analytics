"""How a value of a report table looks: {% report_cell row column %}.

One tag for every report (reports/views.py Column.kind) instead of an
"if kind == ..." chain repeated in each template.
"""

from django import template
from django.template.defaultfilters import floatformat
from django.urls import reverse
from django.utils import formats
from django.utils.html import format_html
from django.utils.translation import gettext as _

from reports.days import report_zone
from sales.models import Order, OrderLine

register = template.Library()


@register.filter
def money(value):
    """1234.5 -> "1 234,50" (uk) / "1,234.50" (en): grouping of the language."""
    return floatformat(value or 0, "2g")


@register.filter
def kyiv(moment):
    """A moment from the database (UTC) in the time of the reports."""
    if not moment:
        return ""
    return formats.date_format(moment.astimezone(report_zone()), "SHORT_DATETIME_FORMAT")


@register.filter
def format_value(value, kind):
    """A value by its kind (reports/views.py Column.kind, Tile.kind)."""
    if kind == "money":
        return money(value)
    if kind == "percent":
        return f"{floatformat(value or 0, 1)}%"
    if kind == "decimal":
        return "" if value is None else floatformat(value, 1)
    if kind == "int":
        return floatformat(value or 0, "0g")
    if kind == "day":
        return formats.date_format(value, "SHORT_DATE_FORMAT")
    if kind == "month":
        return formats.date_format(value, "YEAR_MONTH_FORMAT")
    if kind == "datetime":
        return kyiv(value)
    if kind == "format":
        return OrderLine.FormatType(value).label if value else ""
    if kind == "payment":
        return Order.PaymentStatus(value).label if value else ""
    if kind == "category":
        return value or _("No category")
    if kind == "order":
        return f"#{value}"
    return "" if value is None else value


@register.simple_tag(takes_context=True)
def report_cell(context, row, column):
    value = row.get(column.key)
    if column.kind != "book":
        return format_value(value, column.kind)
    # The book page with the same period as this report
    url = reverse("reports:book", args=[row["book_id"]])
    query = context["request"].GET.copy()
    for name in ("sort", "page", "print", "group"):
        query.pop(name, None)
    if query:
        url = f"{url}?{query.urlencode()}"
    return format_html('<a href="{}">{}</a>', url, value)

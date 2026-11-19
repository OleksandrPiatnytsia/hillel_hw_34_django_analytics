"""CSV and XLSX files of the reports, made by the Celery task (reports/tasks.py).

    ReportExport(pending)  -- run_export() -->
        the class of the report page, without a request (for_export)
        -> get_table(): the same columns and rows as on the screen
        -> CSV or XLSX bytes -> ReportExport(done, content=...)

Values in the files are raw, not formatted for reading: 1234.5 (not
"1 234,50"), dates as dates. A spreadsheet then can sum and sort them; the
CSV can be read by any program. The column names are in the language of the
page the export was started from.
"""

import csv
import io
import logging
from datetime import date, datetime
from decimal import Decimal

from django.conf import settings
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from sales.models import Order, OrderLine

from .days import report_zone
from .models import ReportExport
from .periods import Period

logger = logging.getLogger(__name__)  # "reports.exports"

CONTENT_TYPES = {
    ReportExport.Format.CSV: "text/csv; charset=utf-8",
    ReportExport.Format.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

# Excel number formats of the column kinds (reports/views.py Column.kind)
XLSX_FORMATS = {
    "money": "#,##0.00",
    "decimal": "0.0",
    "percent": "0.0",
    "day": "dd.mm.yyyy",
    "month": "mm.yyyy",
    "datetime": "dd.mm.yyyy hh:mm",
}


class ExportTooLarge(Exception):
    pass


def file_value(value, kind):
    """A table value as it goes into a file: a number, a date or a text."""
    if value is None:
        return _("No category") if kind == "category" else None
    if kind == "datetime":
        # Kyiv time without the zone: Excel has no time zones
        return value.astimezone(report_zone()).replace(tzinfo=None)
    if kind == "format":
        return str(OrderLine.FormatType(value).label)
    if kind == "payment":
        return str(Order.PaymentStatus(value).label)
    return value


def csv_text(value, kind):
    if value is None:
        return ""
    if kind == "month":
        return value.strftime("%Y-%m")
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def write_csv(columns, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([str(column.label) for column in columns])
    for row in rows:
        writer.writerow([csv_text(file_value(row.get(c.key), c.kind), c.kind) for c in columns])
    # utf-8-sig: the "BOM" at the start makes Excel read the Ukrainian
    # letters as UTF-8 instead of a Windows code page
    return buffer.getvalue().encode("utf-8-sig")


def write_xlsx(columns, rows, title):
    workbook = Workbook()
    sheet = workbook.active
    # A sheet name: at most 31 characters, no []:*?/\
    sheet.title = "".join(char for char in str(title) if char not in "[]:*?/\\")[:31] or "Report"
    sheet.append([str(column.label) for column in columns])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        values = [file_value(row.get(column.key), column.kind) for column in columns]
        # Decimal -> float: openpyxl writes numbers, not text
        sheet.append([float(value) if isinstance(value, Decimal) else value for value in values])
    for index, column in enumerate(columns, start=1):
        letter = get_column_letter(index)
        number_format = XLSX_FORMATS.get(column.kind)
        if number_format:
            for (cell,) in sheet.iter_rows(min_row=2, min_col=index, max_col=index):
                cell.number_format = number_format
        width = max(
            [len(str(column.label))] + [len(str(cell.value or "")) for cell in sheet[letter]]
        )
        sheet.column_dimensions[letter].width = min(width + 2, 60)
    # The header stays on the screen while scrolling
    sheet.freeze_panes = "A2"
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def build_file(export):
    """(content, filename) of an export. Raises for a report that can't be built."""
    # Imported here, not at the top: views imports tasks (to start an
    # export), tasks imports this module; a top-level import of views would
    # close the circle while views is still half loaded
    from .views import EXPORTABLE_REPORTS

    params = dict(export.params)
    period = Period(date.fromisoformat(params.pop("from")), date.fromisoformat(params.pop("to")))
    sort = params.pop("sort", "")
    report = EXPORTABLE_REPORTS[export.report].for_export(period, params)
    columns, rows = report.get_table(sort)

    if export.format == ReportExport.Format.CSV:
        content = write_csv(columns, rows)
    else:
        content = write_xlsx(columns, rows, report.title)

    name = export.report if "book" not in params else f"book-{params['book']}"
    return content, f"{name}_{period.first}_{period.last}.{export.format}"


def run_export(export_id):
    """Make the file of one export. Safe to run twice (acks_late): a
    finished export is left as it is."""
    export = ReportExport.objects.get(pk=export_id)
    if export.is_finished:
        return export

    export.status = ReportExport.Status.RUNNING
    export.save(update_fields=["status"])
    try:
        with translation.override(export.language):
            content, filename = build_file(export)
            if len(content) > settings.EXPORT_MAX_BYTES:
                raise ExportTooLarge(_("The file is too large. Choose a shorter period."))
    except ExportTooLarge as error:
        # Expected: not a bug, so a warning, not an error for Sentry
        logger.warning("Export %s too large", export.pk)
        export.status = ReportExport.Status.FAILED
        export.error = str(error)
    except Exception as error:
        # The user sees the reason on the page "My exports"; the details
        # go to the log and to Sentry
        logger.exception("Export %s failed", export.pk)
        export.status = ReportExport.Status.FAILED
        export.error = str(error)[:500] or error.__class__.__name__
    else:
        export.status = ReportExport.Status.DONE
        export.content = content
        export.size = len(content)
        export.filename = filename
        logger.info("Export %s ready: %s, %d bytes", export.pk, filename, len(content))
    export.finished_at = timezone.now()
    export.save()
    return export

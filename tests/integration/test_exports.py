"""CSV / XLSX exports: the button, the Celery task, the list, the download."""

import csv
import io
from datetime import timedelta

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from reports import tasks
from reports.aggregation import rebuild_days
from reports.days import report_zone, today
from reports.exports import run_export
from reports.models import ReportExport
from tests.factories import BookFactory, OrderFactory, OrderLineFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def book():
    """A book sold today: 2 paper copies for 700 UAH."""
    book = BookFactory(title="Kobzar")
    OrderLineFactory(book=book, order=OrderFactory(created_at=timezone.now()))
    rebuild_days([today()])
    return book


@pytest.fixture
def export_now(analyst_client, django_capture_on_commit_callbacks):
    """POST an export form and run its Celery task (eager in the tests).

    The task starts on the commit of the request's transaction; in a test
    nothing is committed, so the callbacks are captured and run here.
    """

    def post(report, **data):
        data.setdefault("period", "7")
        data.setdefault("format", "csv")
        with django_capture_on_commit_callbacks(execute=True):
            response = analyst_client.post(reverse("reports:export_create", args=[report]), data)
        return response

    return post


def download(client, export):
    return client.get(reverse("reports:export_download", args=[export.pk]))


def read_csv(response):
    # utf-8-sig: the BOM for Excel at the start of the file
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


def test_report_page_has_the_export_buttons(analyst_client, book):
    content = analyst_client.get(reverse("reports:sales"), {"period": "7"}).content.decode()

    assert reverse("reports:export_create", args=["sales"]) in content
    assert 'value="xlsx"' in content


def test_dashboard_has_no_export_buttons(analyst_client, book):
    content = analyst_client.get(reverse("reports:dashboard")).content.decode()

    assert "/export/" not in content


def test_csv_export_from_start_to_download(analyst_client, analyst, book, export_now):
    response = export_now("sales", group="day", sort="-revenue_uah")

    assert response.url == reverse("reports:exports")
    export = ReportExport.objects.get()
    assert export.user == analyst
    assert export.status == ReportExport.Status.DONE
    # The real dates are stored, not "the last 7 days"
    assert export.params == {
        "from": (today() - timedelta(days=6)).isoformat(),
        "to": today().isoformat(),
        "group": "day",
        "sort": "-revenue_uah",
    }
    assert export.filename == f"sales_{today() - timedelta(days=6)}_{today()}.csv"

    file = download(analyst_client, export)

    assert file["Content-Type"] == "text/csv; charset=utf-8"
    assert f'filename="{export.filename}"' in file["Content-Disposition"]
    rows = read_csv(file)
    # The language of the page: Ukrainian by default
    assert rows[0][0] == "День"
    assert len(rows) == 1 + 7
    # Sorted as asked: the day with the sale first; raw numbers, ISO dates
    assert rows[1][0] == today().isoformat()
    assert rows[1][4] == "700.00"


def test_export_in_english(analyst_client, export_now, book):
    analyst_client.cookies["django_language"] = "en"

    export_now("formats")

    rows = read_csv(download(analyst_client, ReportExport.objects.get()))
    assert rows[0] == ["Format", "Copies", "Revenue, UAH", "Share of revenue"]
    assert rows[1][0] == "Paper"


def test_xlsx_export_has_numbers_and_dates(analyst_client, export_now, book):
    export_now("sales", format="xlsx", group="day", sort="day")

    export = ReportExport.objects.get()
    file = download(analyst_client, export)
    sheet = load_workbook(io.BytesIO(file.content)).active

    assert file["Content-Type"].startswith("application/vnd.openxmlformats")
    assert sheet["A1"].value == "День"
    last = sheet.max_row
    # A real date and a real number, not texts: Excel can sum and sort them
    assert sheet.cell(last, 1).value.date() == today()
    assert sheet.cell(last, 5).value == 700
    assert sheet.cell(last, 5).number_format == "#,##0.00"
    assert sheet.freeze_panes == "A2"


def test_book_export(analyst_client, export_now, book):
    export_now("book", book=book.pk)

    export = ReportExport.objects.get()
    assert export.params["book"] == book.pk
    assert export.filename.startswith(f"book-{book.pk}_")
    assert len(read_csv(download(analyst_client, export))) == 1 + 7


def test_cancellations_export_has_kyiv_times(analyst_client, export_now):
    order = OrderFactory(created_at=timezone.now(), status="cancelled")
    OrderLineFactory(order=order)

    export_now("cancellations")

    rows = read_csv(download(analyst_client, ReportExport.objects.get()))
    kyiv_time = order.created_at.astimezone(report_zone()).strftime("%Y-%m-%d %H:%M")
    assert rows[1][:2] == [str(order.source_id), kyiv_time]


def test_categories_export_names_the_books_without_category(analyst_client, export_now, book):
    export_now("categories")

    rows = read_csv(download(analyst_client, ReportExport.objects.get()))
    assert rows[1][0] == "Без категорії"


@pytest.mark.parametrize(
    "report, data",
    [("dashboard", {}), ("sales", {"format": "pdf"}), ("book", {"book": "999"}), ("book", {})],
)
def test_unknown_report_format_or_book_is_404(analyst_client, report, data):
    url = reverse("reports:export_create", args=[report])

    assert analyst_client.post(url, {"format": "csv", **data}).status_code == 404
    assert not ReportExport.objects.exists()


def test_bad_period_goes_back_with_a_message(analyst_client):
    response = analyst_client.post(
        reverse("reports:export_create", args=["sales"]),
        {"format": "csv", "from": "2026-11-19", "to": "2026-11-01"},
        HTTP_REFERER="/reports/sales/",
    )

    assert response.url == "/reports/sales/"
    assert list(get_messages(response.wsgi_request))
    assert not ReportExport.objects.exists()


def test_export_needs_the_permission(client, user_client):
    url = reverse("reports:export_create", args=["sales"])

    assert reverse("users:login") in client.post(url, {"format": "csv"}).url
    assert user_client.post(url, {"format": "csv"}).status_code == 403
    # GET is not a way to start an export
    assert user_client.get(url).status_code in (403, 405)


def test_only_the_author_downloads_a_ready_file(client, analyst_client, export_now, book):
    export_now("sales")
    export = ReportExport.objects.get()
    other = UserFactory(is_superuser=True)
    client.force_login(other)

    assert download(client, export).status_code == 404
    export.status = ReportExport.Status.PENDING
    export.save()
    assert download(analyst_client, export).status_code == 404


def test_my_exports_list(analyst_client, analyst, export_now, book):
    export_now("sales")
    ReportExport.objects.create(
        user=UserFactory(), report="sales", format="csv", language="uk", params={}
    )

    response = analyst_client.get(reverse("reports:exports"))

    exports = list(response.context["object_list"])
    assert [export.user for export in exports] == [analyst]
    assert exports[0].report_title == "Продажі"
    assert response.context["waiting"] is False
    assert reverse("reports:export_download", args=[exports[0].pk]) in response.content.decode()


def test_my_exports_refresh_while_a_file_is_made(analyst_client, analyst):
    ReportExport.objects.create(
        user=analyst, report="book", format="csv", language="uk", params={"book": 1}
    )

    response = analyst_client.get(reverse("reports:exports"))

    assert response.context["waiting"] is True
    assert 'http-equiv="refresh"' in response.content.decode()
    assert response.context["object_list"][0].report_title == "Книга"


# --- The task --------------------------------------------------------------------


def make_export(user, **fields):
    defaults = {
        "report": "sales",
        "format": "csv",
        "language": "uk",
        "params": {"from": "2026-11-01", "to": "2026-11-19"},
    }
    return ReportExport.objects.create(user=user, **{**defaults, **fields})


def test_finished_export_is_not_made_again(analyst):
    export = make_export(analyst, status=ReportExport.Status.DONE, filename="kept.csv")

    assert run_export(export.pk).filename == "kept.csv"


def test_broken_export_fails_with_the_reason(analyst):
    export = make_export(analyst, params={"from": "2026-11-01"})

    result = tasks.generate_export.delay(export.pk).get()

    export.refresh_from_db()
    assert result == "failed"
    assert export.error
    assert export.finished_at is not None


def test_too_large_file_fails(analyst, settings):
    settings.EXPORT_MAX_BYTES = 10
    export = make_export(analyst)

    run_export(export.pk)

    export.refresh_from_db()
    assert export.status == ReportExport.Status.FAILED
    assert "завеликий" in export.error


def test_old_exports_are_deleted(analyst):
    old = make_export(analyst)
    ReportExport.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=8))
    fresh = make_export(analyst)

    assert tasks.delete_old_exports.delay().get() == 1
    assert list(ReportExport.objects.all()) == [fresh]

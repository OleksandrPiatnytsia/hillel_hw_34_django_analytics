"""The dashboard, the report pages, the orders and the events journal."""

import json
from datetime import timedelta

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from events.models import Event
from reports.aggregation import rebuild_days
from reports.days import today
from sales.models import Order
from tests.factories import BookFactory, OrderFactory, OrderLineFactory, UserFactory

pytestmark = pytest.mark.django_db

REPORTS = ["sales", "books", "formats", "categories", "customers", "cancellations"]


@pytest.fixture
def book():
    """A book sold today and yesterday, and the totals of both days."""
    book = BookFactory(title="Kobzar")
    now = timezone.now()
    for created_at in (now, now - timedelta(days=1)):
        OrderLineFactory(book=book, order=OrderFactory(created_at=created_at))
    OrderLineFactory(book=book, order=OrderFactory(created_at=now, status=Order.Status.CANCELLED))
    rebuild_days([today(), today() - timedelta(days=1)])
    return book


def chart_data(response, name="main"):
    return response.context["charts"][name]


# --- Access ------------------------------------------------------------------


@pytest.mark.parametrize("name", ["dashboard", *REPORTS, "orders"])
def test_pages_need_a_login(client, name):
    response = client.get(reverse(f"reports:{name}"))

    assert response.status_code == 302
    assert reverse("users:login") in response.url


@pytest.mark.parametrize("name", ["dashboard", *REPORTS, "orders", "events"])
def test_pages_are_closed_without_the_permission(user_client, name):
    assert user_client.get(reverse(f"reports:{name}")).status_code == 403


def test_events_journal_is_not_for_analysts(analyst_client):
    assert analyst_client.get(reverse("reports:events")).status_code == 403


# --- Dashboard ---------------------------------------------------------------


def test_dashboard_without_data(analyst_client):
    response = analyst_client.get(reverse("reports:dashboard"))

    assert response.context["has_data"] is False
    assert "chart.umd.min.js" not in response.content.decode()


def test_dashboard_with_data(analyst_client, book):
    response = analyst_client.get(reverse("reports:dashboard"), {"period": "7"})

    assert response.status_code == 200
    assert response.context["has_data"] is True
    tiles = {item["tile"].key: item for item in response.context["tiles"]}
    assert tiles["orders"]["value"] == 3
    assert tiles["revenue_uah"]["value"] == 1400
    assert set(response.context["charts"]) == {"revenue", "books", "formats", "categories"}
    assert chart_data(response, "books")["labels"] == ["Kobzar"]
    assert len(chart_data(response, "revenue")["labels"]) == 7
    # The chart data is on the page for Chart.js
    assert 'id="chart-revenue"' in response.content.decode()


def test_bad_period_falls_back_to_the_default_with_a_message(analyst_client):
    response = analyst_client.get(reverse("reports:dashboard"), {"from": "2026-11-19", "to": "x"})

    assert response.status_code == 200
    assert response.context["period"].preset == 30
    assert [str(message) for message in get_messages(response.wsgi_request)]


# --- Reports -----------------------------------------------------------------


@pytest.mark.parametrize("name", REPORTS)
def test_every_report_renders(analyst_client, book, name):
    response = analyst_client.get(reverse(f"reports:{name}"), {"period": "7"})

    assert response.status_code == 200
    assert "reports/report.html" in [template.name for template in response.templates]
    assert response.context["tiles"]


def test_tiles_compare_with_the_previous_period(analyst_client, book):
    # Today only vs yesterday only: one order each
    day = today().isoformat()
    response = analyst_client.get(reverse("reports:sales"), {"from": day, "to": day})

    tiles = {item["tile"].key: item for item in response.context["tiles"]}
    assert tiles["orders"]["value"] == 2
    assert tiles["orders"]["previous"] == 1
    assert tiles["orders"]["direction"] == "up"
    assert tiles["orders"]["tone"] == "success"


def test_more_cancellations_is_red(analyst_client, book):
    day = today().isoformat()
    response = analyst_client.get(reverse("reports:cancellations"), {"from": day, "to": day})

    tiles = {item["tile"].key: item for item in response.context["tiles"]}
    assert tiles["cancelled_orders"]["tone"] == "danger"
    assert len(response.context["rows"]) == 1


@pytest.mark.parametrize("group", ["day", "week", "month"])
def test_sales_groups(analyst_client, book, group):
    response = analyst_client.get(reverse("reports:sales"), {"period": "30", "group": group})

    assert response.context["group"] == group
    assert sum(row["orders"] for row in response.context["page_obj"].paginator.object_list) == 3


def test_unknown_group_is_day(analyst_client, book):
    response = analyst_client.get(reverse("reports:sales"), {"group": "year"})

    assert response.context["group"] == "day"


def test_sorting_and_its_links(analyst_client, book):
    OrderLineFactory(
        book=BookFactory(title="Atlas"),
        order=OrderFactory(created_at=timezone.now()),
        quantity=1,
        amount_uah=100,
    )
    rebuild_days([today()])

    by_revenue = analyst_client.get(reverse("reports:books"), {"period": "7"})
    by_title = analyst_client.get(reverse("reports:books"), {"period": "7", "sort": "title"})
    unknown = analyst_client.get(reverse("reports:books"), {"period": "7", "sort": "password"})

    assert [row["title"] for row in by_revenue.context["rows"]] == ["Kobzar", "Atlas"]
    assert [row["title"] for row in by_title.context["rows"]] == ["Atlas", "Kobzar"]
    assert unknown.context["headers"][3]["state"] == "desc"
    headers = {header["column"].key: header for header in by_title.context["headers"]}
    # A second click on the sorted column turns the order around
    assert headers["title"]["state"] == "asc"
    assert headers["title"]["next_sort"] == "-title"
    assert headers["revenue_uah"]["next_sort"] == "-revenue_uah"


def test_pages_of_a_long_table(analyst_client, book):
    response = analyst_client.get(reverse("reports:sales"), {"period": "90"})

    assert len(response.context["rows"]) == 25
    assert response.context["page_obj"].paginator.num_pages == 4


def test_print_view_has_every_row(analyst_client, book):
    response = analyst_client.get(reverse("reports:sales"), {"period": "90", "print": "1"})

    assert len(response.context["rows"]) == 90
    assert "data-autoprint" in response.content.decode()


def test_book_link_keeps_the_period(analyst_client, book):
    response = analyst_client.get(reverse("reports:books"), {"period": "7", "sort": "title"})

    link = reverse("reports:book", args=[book.pk]) + "?period=7"
    assert f'href="{link}"' in response.content.decode()


def test_book_page(analyst_client, book):
    response = analyst_client.get(reverse("reports:book", args=[book.pk]), {"period": "7"})

    assert response.status_code == 200
    assert response.context["title"] == "Kobzar"
    tiles = {item["tile"].key: item for item in response.context["tiles"]}
    assert tiles["quantity"]["value"] == 4
    assert response.context["format_rows"][0]["format_type"] == "paper"
    assert json.loads(json.dumps(chart_data(response, "formats")))["labels"]


def test_unknown_book_is_404(analyst_client):
    assert analyst_client.get(reverse("reports:book", args=[999])).status_code == 404


def test_categories_note(analyst_client, book):
    response = analyst_client.get(reverse("reports:categories"))

    assert response.context["note"]


def test_answers_come_from_the_cache(analyst_client, book, django_assert_max_num_queries):
    url = reverse("reports:books")
    analyst_client.get(url, {"period": "7"})

    # The second view of the same report: no report queries, only the
    # session, the user and the permissions
    with django_assert_max_num_queries(4):
        analyst_client.get(url, {"period": "7"})


# --- Orders and events ---------------------------------------------------------


def test_orders_list_and_filters(analyst_client):
    OrderFactory(source_id=101)
    OrderFactory(source_id=102, status=Order.Status.CANCELLED)
    OrderFactory(source_id=103, payment_status=Order.PaymentStatus.PAID)
    url = reverse("reports:orders")

    def numbers(**query):
        response = analyst_client.get(url, query)
        return sorted(order.source_id for order in response.context["object_list"])

    assert numbers() == [101, 102, 103]
    assert numbers(status="cancelled") == [102]
    assert numbers(payment="paid") == [103]
    assert numbers(number="101") == [101]
    # Unknown values are ignored, not an error
    assert numbers(status="lost", number="abc") == [101, 102, 103]


def test_events_journal_for_a_superuser(client):
    Event.objects.create(
        event_id="7d0f3c55-6a51-4c84-9a54-0d1f7b6f0b11",
        type="order.created",
        status=Event.Status.PROCESSED,
        payload={"order": {"id": 5}},
    )
    Event.objects.create(
        event_id="7d0f3c55-6a51-4c84-9a54-0d1f7b6f0b12",
        status=Event.Status.FAILED,
        error="order: This field is required.",
    )
    client.force_login(UserFactory(is_superuser=True, is_staff=True))
    url = reverse("reports:events")

    everything = client.get(url)
    failed = client.get(url, {"status": "failed"})
    created = client.get(url, {"type": "order.created"})

    assert everything.context["failed_count"] == 1
    assert len(everything.context["object_list"]) == 2
    assert [event.status for event in failed.context["object_list"]] == ["failed"]
    assert len(created.context["object_list"]) == 1
    assert "#5" in everything.content.decode()


def test_navbar_shows_the_reports(analyst_client):
    content = analyst_client.get(reverse("reports:dashboard")).content.decode()

    assert reverse("reports:sales") in content
    assert reverse("reports:orders") in content
    # The events journal is not for analysts
    assert reverse("reports:events") not in content

"""The REST API of the reports (reports/api.py): JWT, permissions, periods,
answers, the cache and the limit of requests."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from reports.aggregation import rebuild_days
from reports.days import today
from sales.models import Order, OrderLine
from tests.factories import PASSWORD, BookFactory, OrderFactory, OrderLineFactory

pytestmark = pytest.mark.django_db

ENDPOINTS = ["summary", "daily", "top_books", "formats"]


def url(name):
    return reverse(f"api:reports_{name}")


@pytest.fixture
def sales():
    """Today: an order with 2 paper copies (700 UAH) and a cancelled one;
    yesterday: an e-book order (300 UAH)."""
    book = BookFactory(title="Kobzar", source_id=42)
    now = timezone.now()
    OrderLineFactory(book=book, order=OrderFactory(created_at=now))
    OrderLineFactory(book=book, order=OrderFactory(created_at=now, status=Order.Status.CANCELLED))
    OrderLineFactory(
        book=BookFactory(title="Atlas"),
        order=OrderFactory(created_at=now - timedelta(days=1), total="300"),
        format_type=OrderLine.FormatType.EBOOK,
        quantity=1,
        amount_uah="300",
    )
    rebuild_days([today(), today() - timedelta(days=1)])


@pytest.fixture
def service_api(service_account):
    """An API client with a JWT of the bookstore's service account, got as
    the bookstore gets it: POST /api/token/."""
    client = APIClient()
    tokens = client.post(
        reverse("api:token_obtain_pair"),
        {"username": service_account.username, "password": PASSWORD},
    ).json()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return client


# --- Access ----------------------------------------------------------------------


@pytest.mark.parametrize("name", ENDPOINTS)
def test_no_token_is_401(name):
    response = APIClient().get(url(name))

    assert response.status_code == 401
    assert response["WWW-Authenticate"].startswith("Bearer")


def test_broken_token_is_401():
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer not-a-token")

    assert client.get(url("summary")).status_code == 401


@pytest.mark.parametrize("name", ENDPOINTS)
def test_account_without_the_permission_is_403(user, name):
    client = APIClient()
    client.force_authenticate(user)

    response = client.get(url(name), HTTP_ACCEPT_LANGUAGE="en")

    assert response.status_code == 403
    assert "no access to the reports API" in response.json()["detail"]


def test_analyst_may_use_the_api_with_the_site_session(analyst_client):
    """The session of the site login: Swagger in the same browser."""
    assert analyst_client.get(url("summary")).status_code == 200


# --- Answers ---------------------------------------------------------------------


def test_summary(service_api, sales):
    day = today().isoformat()

    response = service_api.get(url("summary"), {"from": day, "to": day})

    assert response.status_code == 200
    data = response.json()
    assert data["period"] == {"from": day, "to": day, "days": 1}
    yesterday = (today() - timedelta(days=1)).isoformat()
    assert data["previous_period"] == {"from": yesterday, "to": yesterday, "days": 1}
    assert data["totals"]["orders"] == 2
    assert data["totals"]["revenue_uah"] == "700.00"
    assert data["totals"]["cancelled_share"] == "50.0"
    assert data["previous_totals"]["revenue_uah"] == "300.00"
    # 300 -> 700: +133.3 %
    assert data["changes"]["revenue_uah"] == "133.3"


def test_summary_of_a_period_after_an_empty_one_has_null_changes(service_api, sales):
    day = (today() - timedelta(days=1)).isoformat()

    data = service_api.get(url("summary"), {"from": day, "to": day}).json()

    assert data["changes"]["orders"] is None


def test_daily_has_every_day(service_api, sales):
    data = service_api.get(url("daily"), {"period": "7"}).json()

    assert data["period"]["days"] == 7
    assert len(data["days"]) == 7
    assert data["days"][-1]["day"] == today().isoformat()
    assert data["days"][-1]["revenue_uah"] == "700.00"
    assert data["days"][0]["orders"] == 0


def test_default_period_is_30_days(service_api, sales):
    data = service_api.get(url("daily")).json()

    assert data["period"]["days"] == 30


def test_top_books_with_the_bookstore_ids(service_api, sales):
    data = service_api.get(url("top_books"), {"period": "7"}).json()

    assert [book["title"] for book in data["books"]] == ["Kobzar", "Atlas"]
    assert data["books"][0] == {
        "source_id": 42,
        "title": "Kobzar",
        "author": "Author",
        "quantity": 2,
        "revenue_uah": "700.00",
    }


def test_top_books_limit(service_api, sales):
    data = service_api.get(url("top_books"), {"period": "7", "limit": 1}).json()

    assert len(data["books"]) == 1


def test_formats(service_api, sales):
    data = service_api.get(url("formats"), {"period": "7"}).json()

    shares = {row["format_type"]: row["revenue_share"] for row in data["formats"]}
    assert shares == {"paper": "70.0", "ebook": "30.0"}


# --- Bad parameters ----------------------------------------------------------------


@pytest.mark.parametrize(
    "query, field",
    [
        ({"period": "5"}, "period"),
        ({"from": "19.11.2026", "to": "2026-11-19"}, "from"),
        ({"from": "2026-11-19"}, "non_field_errors"),
        ({"from": "2026-11-19", "to": "2026-11-01"}, "non_field_errors"),
        ({"from": "2025-01-01", "to": "2026-11-19"}, "non_field_errors"),
    ],
)
def test_bad_period_is_400_with_a_reason(service_api, query, field):
    response = service_api.get(url("summary"), query)

    assert response.status_code == 400
    assert response.json()[field]


@pytest.mark.parametrize("limit", ["0", "51", "many"])
def test_bad_limit_is_400(service_api, limit):
    response = service_api.get(url("top_books"), {"limit": limit})

    assert response.status_code == 400
    assert "limit" in response.json()


def test_errors_in_the_language_of_the_request(service_api):
    response = service_api.get(
        url("summary"),
        {"from": "2026-11-19", "to": "2026-11-01"},
        HTTP_ACCEPT_LANGUAGE="uk",
    )

    assert response.json()["non_field_errors"] == ["Початок періоду пізніший за його кінець."]


# --- Cache, logging, limits ----------------------------------------------------------


def test_answer_comes_from_the_cache_until_a_recalculation(service_api, sales):
    first = service_api.get(url("summary"), {"period": "7"}).json()
    OrderLineFactory(order=OrderFactory(created_at=timezone.now()))

    # The new order is in the database, but the day is not recalculated yet
    assert service_api.get(url("summary"), {"period": "7"}).json() == first

    rebuild_days([today()])

    assert service_api.get(url("summary"), {"period": "7"}).json()["totals"]["orders"] == 4


def test_calls_are_logged(service_api, sales, caplog):
    with caplog.at_level("INFO", logger="reports.api"):
        service_api.get(url("formats"), {"period": "7"})

    assert "API formats by bookstore-service" in caplog.text


def test_requests_are_limited(service_api):
    from rest_framework.settings import api_settings
    from rest_framework.throttling import ScopedRateThrottle

    # The rates are read once, when the throttle class is imported:
    # set a low rate for this test and put the real one back after it
    rates = {**api_settings.DEFAULT_THROTTLE_RATES, "reports": "2/minute"}
    original = ScopedRateThrottle.THROTTLE_RATES
    ScopedRateThrottle.THROTTLE_RATES = rates
    try:
        statuses = [service_api.get(url("formats")).status_code for _ in range(3)]
    finally:
        ScopedRateThrottle.THROTTLE_RATES = original

    assert statuses == [200, 200, 429]


def test_reports_are_in_swagger(client):
    schema = client.get(reverse("api:schema")).content.decode()

    for path in ("/api/reports/summary/", "/api/reports/top-books/"):
        assert path in schema

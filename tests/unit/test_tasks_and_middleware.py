"""The Celery task of the users app and the request logging middleware."""

from datetime import timedelta

import pytest
from django.contrib.sessions.models import Session
from django.urls import reverse
from django.utils import timezone

from users.tasks import clear_expired_sessions


# Generated with AI
@pytest.mark.django_db
def test_clear_expired_sessions_deletes_only_the_expired_ones():
    now = timezone.now()
    Session.objects.create(session_key="old", session_data="", expire_date=now - timedelta(days=1))
    Session.objects.create(session_key="new", session_data="", expire_date=now + timedelta(days=1))

    clear_expired_sessions.delay()  # eager in tests: runs right here

    assert list(Session.objects.values_list("session_key", flat=True)) == ["new"]


# Generated with AI
@pytest.mark.django_db
def test_every_request_is_timed_and_logged(analyst_client, caplog):
    caplog.set_level("INFO", logger="config.middleware")

    response = analyst_client.get(reverse("reports:dashboard"), {"page": "2"})

    assert response["X-Request-Duration"].endswith("ms")
    assert response["Server-Timing"].startswith("app;dur=")
    assert "GET /?page=2 200" in caplog.text
    assert "user=analyst" in caplog.text


# Generated with AI
@pytest.mark.django_db
def test_health_is_not_logged(client, caplog):
    caplog.set_level("INFO", logger="config.middleware")

    client.get(reverse("health"))

    assert "/health/" not in caplog.text


# Generated with AI
@pytest.mark.django_db
def test_slow_request_is_a_warning(client, settings, caplog):
    # Read when the middleware is created: the first request of this client
    settings.REQUEST_SLOW_MS = 0

    client.get(reverse("users:login"))

    [record] = [record for record in caplog.records if record.name == "config.middleware"]
    assert record.levelname == "WARNING"
    assert "/accounts/login/ 200" in record.getMessage()

"""GET /health/: the healthcheck of docker compose (and of Railway)."""

import pytest
from django.urls import reverse

from config import views


# Generated with AI
@pytest.mark.django_db
def test_health_ok_when_database_and_cache_answer(client):
    response = client.get(reverse("health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "cache": "ok"}
    assert "no-cache" in response["Cache-Control"]


# Generated with AI
@pytest.mark.django_db
def test_health_503_when_a_service_is_down(client, monkeypatch, caplog):
    async def broken_cache():
        raise ConnectionError("redis is down")

    monkeypatch.setitem(views.CHECKS, "cache", broken_cache)

    response = client.get(reverse("health"))

    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "ok", "cache": "error"}
    # The details only in the log, never in the public answer
    assert "redis is down" not in response.content.decode()
    assert "Health check failed: cache" in caplog.text


# Generated with AI
def test_health_accepts_only_get(client):
    assert client.post(reverse("health")).status_code == 405

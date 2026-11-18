"""The REST API skeleton: JWT tokens and the Swagger documentation."""

import pytest
from django.urls import reverse

from ..factories import PASSWORD


# Generated with AI
@pytest.mark.django_db
def test_token_pair_for_a_service_account(client, service_account):
    response = client.post(
        reverse("api:token_obtain_pair"),
        {"username": service_account.username, "password": PASSWORD},
    )

    assert response.status_code == 200
    tokens = response.json()
    assert set(tokens) == {"access", "refresh"}

    refreshed = client.post(reverse("api:token_refresh"), {"refresh": tokens["refresh"]})
    assert refreshed.status_code == 200
    assert "access" in refreshed.json()


# Generated with AI
@pytest.mark.django_db
def test_wrong_password_gets_no_token(client, service_account):
    response = client.post(
        reverse("api:token_obtain_pair"),
        {"username": service_account.username, "password": "wrong"},
    )

    assert response.status_code == 401


# Generated with AI
@pytest.mark.django_db
def test_token_requests_are_limited(client, service_account):
    url = reverse("api:token_obtain_pair")
    data = {"username": service_account.username, "password": "wrong"}

    statuses = [client.post(url, data).status_code for _ in range(11)]

    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429  # "token": "10/minute"


# Generated with AI
@pytest.mark.django_db
def test_schema_and_swagger_are_public(client):
    """Open on purpose: the documentation shows only the shape of the API;
    every endpoint itself still needs a token (DEFAULT_PERMISSION_CLASSES)."""
    schema = client.get(reverse("api:schema"))
    assert schema.status_code == 200
    assert b"/api/token/" in schema.content

    docs = client.get(reverse("api:docs"))
    assert docs.status_code == 200
    assert b"swagger-ui" in docs.content

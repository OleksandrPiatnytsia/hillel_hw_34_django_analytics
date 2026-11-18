"""The two languages of the interface (uk by default, en on request)."""

import pytest
from django.conf import settings
from django.urls import reverse


# Generated with AI
@pytest.mark.django_db
def test_ukrainian_by_default(client):
    response = client.get(reverse("users:login"))

    assert response.headers["Content-Language"] == "uk"
    assert "Увійти" in response.content.decode()


# Generated with AI
@pytest.mark.django_db
def test_switcher_sets_the_cookie_and_returns_back(client):
    response = client.post(reverse("set_language"), {"language": "en", "next": "/accounts/login/"})

    assert response.status_code == 302
    assert response.url == "/accounts/login/"
    assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "en"

    page = client.get(reverse("users:login"))
    assert page.headers["Content-Language"] == "en"
    assert "Log in" in page.content.decode()


# Generated with AI
@pytest.mark.django_db
def test_unsupported_language_is_never_activated(client):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "de"

    response = client.get(reverse("users:login"))

    assert response.headers["Content-Language"] == "uk"

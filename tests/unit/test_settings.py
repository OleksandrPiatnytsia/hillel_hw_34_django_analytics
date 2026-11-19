"""The settings modules themselves: production refuses unsafe values."""

import importlib
import sys

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from config.version import deployed_commit


def load_production(monkeypatch, **variables):
    """Import config.settings.production anew with these variables.

    A fresh import every time: Python keeps an imported module, and the
    checks at its top level would not run again.
    """
    for name, value in variables.items():
        monkeypatch.setenv(name, value)
    sys.modules.pop("config.settings.production", None)
    sys.modules.pop("config.settings.base", None)
    try:
        return importlib.import_module("config.settings.production")
    finally:
        sys.modules.pop("config.settings.production", None)
        sys.modules.pop("config.settings.base", None)


# Generated with AI
def test_production_needs_allowed_hosts(monkeypatch):
    monkeypatch.delenv("RAILWAY_PUBLIC_DOMAIN", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)

    with pytest.raises(ImproperlyConfigured, match="DJANGO_ALLOWED_HOSTS"):
        load_production(monkeypatch, DJANGO_ALLOWED_HOSTS="")


# Generated with AI
def test_production_is_strict(monkeypatch):
    production = load_production(
        monkeypatch, DJANGO_ALLOWED_HOSTS="analytics.example.com", DJANGO_DEBUG="True"
    )

    assert production.DEBUG is False  # DJANGO_DEBUG is ignored on a server
    assert production.SECURE_SSL_REDIRECT is True
    assert production.SESSION_COOKIE_SECURE is True
    assert "whitenoise.middleware.WhiteNoiseMiddleware" in production.MIDDLEWARE


# Generated with AI
def test_production_adds_the_railway_hosts(monkeypatch):
    production = load_production(
        monkeypatch,
        DJANGO_ALLOWED_HOSTS="",
        RAILWAY_PUBLIC_DOMAIN="analytics.up.railway.app",
        RAILWAY_ENVIRONMENT_NAME="production",
    )

    assert production.ALLOWED_HOSTS == ["analytics.up.railway.app", "healthcheck.railway.app"]


# Generated with AI
def test_local_docker_turns_https_off(monkeypatch):
    production = load_production(
        monkeypatch, DJANGO_ALLOWED_HOSTS="localhost", DJANGO_HTTPS="False"
    )

    assert getattr(production, "SECURE_SSL_REDIRECT", False) is False


# Generated with AI
def test_two_languages_ukrainian_first():
    assert [code for code, _name in settings.LANGUAGES] == ["uk", "en"]
    assert settings.LANGUAGE_CODE == "uk"
    assert settings.TIME_ZONE == "UTC"


# Generated with AI
def test_custom_user_model():
    assert settings.AUTH_USER_MODEL == "users.User"


# Generated with AI
def test_deployed_commit_comes_from_railway_or_app_commit(monkeypatch):
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    monkeypatch.delenv("APP_COMMIT", raising=False)
    assert deployed_commit() == ""

    monkeypatch.setenv("APP_COMMIT", "abc")
    assert deployed_commit() == "abc"

    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "def")
    assert deployed_commit() == "def"


# The mailer of the daily sales email: Brevo, Gmail or the console.
# Every email variable is given (empty or not): a value from a local .env
# must not decide the result (load_dotenv never overrides a set variable).
NO_EMAIL = {"BREVO_API_KEY": "", "EMAIL_FROM": "", "EMAIL_HOST_USER": "", "EMAIL_HOST_PASSWORD": ""}


def test_brevo_needs_a_sender(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="EMAIL_FROM"):
        load_production(
            monkeypatch,
            DJANGO_ALLOWED_HOSTS="analytics.example.com",
            **{**NO_EMAIL, "BREVO_API_KEY": "xkeysib-test"},
        )


@pytest.mark.parametrize(
    "variables, backend, sender",
    [
        (
            {"BREVO_API_KEY": "xkeysib-test", "EMAIL_FROM": "reports@example.com"},
            "anymail.backends.brevo.EmailBackend",
            "reports@example.com",
        ),
        (
            {"EMAIL_HOST_USER": "me@gmail.com", "EMAIL_HOST_PASSWORD": "abcd efgh ijkl mnop"},
            "django.core.mail.backends.smtp.EmailBackend",
            "me@gmail.com",
        ),
        ({}, "django.core.mail.backends.console.EmailBackend", "noreply@localhost"),
    ],
)
def test_mailer_choice(monkeypatch, variables, backend, sender):
    production = load_production(
        monkeypatch, DJANGO_ALLOWED_HOSTS="analytics.example.com", **{**NO_EMAIL, **variables}
    )

    assert production.MAILERS["default"]["BACKEND"] == backend
    assert production.DEFAULT_FROM_EMAIL == f"Bookstore analytics <{sender}>"

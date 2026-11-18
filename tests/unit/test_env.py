"""config/env.py: reading the settings from environment variables."""

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.env import database_settings, env_bool, env_list, redis_url


# Generated with AI
@pytest.mark.parametrize(
    "value, expected",
    [("True", True), ("1", True), (" yes ", True), ("on", True), ("False", False), ("x", False)],
)
def test_env_bool_reads_the_usual_words(monkeypatch, value, expected):
    monkeypatch.setenv("FLAG", value)

    assert env_bool("FLAG", default=None) is expected


# Generated with AI
def test_env_bool_default_when_not_set(monkeypatch):
    monkeypatch.delenv("FLAG", raising=False)

    assert env_bool("FLAG", default=True) is True


# Generated with AI
def test_env_list_splits_and_drops_empty_items(monkeypatch):
    monkeypatch.setenv("HOSTS", " a.com, b.com,,")

    assert env_list("HOSTS") == ["a.com", "b.com"]


# Generated with AI
def test_database_from_postgres_variables(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_DB", "analytics")
    monkeypatch.setenv("POSTGRES_USER", "ann")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("POSTGRES_HOST", "db")
    monkeypatch.setenv("POSTGRES_PORT", "5432")

    database = database_settings()

    assert (database["NAME"], database["USER"], database["HOST"], database["PORT"]) == (
        "analytics",
        "ann",
        "db",
        "5432",
    )


# Generated with AI
def test_database_url_wins_and_is_decoded(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://ann:p%40ss@db.internal:6543/analytics?sslmode=require"
    )

    database = database_settings()

    assert database["PASSWORD"] == "p@ss"  # %40 -> @
    assert database["HOST"] == "db.internal"
    assert database["PORT"] == "6543"
    assert database["OPTIONS"] == {"sslmode": "require"}


# Generated with AI
def test_database_url_must_be_postgresql(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql://ann@db/analytics")

    with pytest.raises(ImproperlyConfigured):
        database_settings()


# Generated with AI
def test_redis_url_replaces_the_database_number():
    assert redis_url("redis://redis:6379", 1) == "redis://redis:6379/1"
    assert redis_url("redis://:secret@redis:6379/0", 1) == "redis://:secret@redis:6379/1"

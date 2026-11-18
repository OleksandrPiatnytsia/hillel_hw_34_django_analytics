"""Fixtures shared by all tests (pytest finds this file by its name).

A fixture = a function whose result pytest passes to every test that has an
argument with the same name:

    def test_dashboard(analyst_client): ...

Fixtures from pytest-django used in the tests:
    db        access to the test database (every test in its own
              transaction, rolled back at the end)
    client    django.test.Client, not logged in
    settings  change a setting for one test, restored afterwards

The groups "Analysts" and "Services" exist in the test database: migrate
sends post_migrate, and users.groups.create_groups makes them.
"""

import pytest
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import Client

from users.groups import ANALYSTS, SERVICES

from .factories import UserFactory


@pytest.fixture(autouse=True)
def _empty_cache():
    """For EVERY test: an empty cache (LocMemCache lives as long as the
    pytest process, so a value or a throttle counter of one test would be
    seen by the next one)."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def user(db):
    """A logged-out user without groups: no access to the analytics pages."""
    return UserFactory()


@pytest.fixture
def analyst(db):
    analyst = UserFactory(username="analyst")
    analyst.groups.add(Group.objects.get(name=ANALYSTS))
    return analyst


@pytest.fixture
def service_account(db):
    account = UserFactory(username="bookstore-service")
    account.groups.add(Group.objects.get(name=SERVICES))
    return account


@pytest.fixture
def analyst_client(analyst):
    client = Client()
    client.force_login(analyst)
    return client


@pytest.fixture
def user_client(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def purged_queues():
    """Empty queues of kombu's memory transport (memory:// in the tests).

    The memory transport keeps its queues in the process for the whole
    test run: a message left by one test would be read by the next one.
    """
    from events.topology import connect, dead_letter_queue, declare_topology, events_queue

    with connect() as connection:
        channel = connection.default_channel
        declare_topology(channel)
        for queue in (events_queue(), dead_letter_queue()):
            queue(channel).purge()
    yield

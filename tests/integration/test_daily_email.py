"""The daily sales email to the Analysts (reports/emails.py, reports/tasks.py)."""

import csv
import io
import smtplib
from datetime import date, datetime, timedelta, timezone
from unittest import mock

import pytest
from celery.exceptions import Retry
from django.contrib.auth.models import Group
from django.core import mail

from reports import tasks
from reports.aggregation import rebuild_days
from reports.emails import recipients, send_daily_sales_email
from tests.factories import BookFactory, OrderFactory, OrderLineFactory, UserFactory
from users.groups import ANALYSTS

pytestmark = pytest.mark.django_db

DAY = date(2026, 11, 18)
# 12:00 in Kyiv
NOON = datetime(2026, 11, 18, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def analysts():
    group = Group.objects.get(name=ANALYSTS)
    first = UserFactory(email="ann@example.com")
    second = UserFactory(email="bob@example.com")
    # Not sent to: without an email, blocked, not an analyst
    no_email = UserFactory(email="")
    blocked = UserFactory(email="old@example.com", is_active=False)
    UserFactory(email="stranger@example.com")
    group.user_set.add(first, second, no_email, blocked)
    return ["ann@example.com", "bob@example.com"]


@pytest.fixture
def sales():
    """The day: 2 orders of "Kobzar" (700 UAH each); the day before: 1 order."""
    book = BookFactory(title="Kobzar & Co")
    for created_at in (NOON, NOON, NOON - timedelta(days=1)):
        OrderLineFactory(book=book, order=OrderFactory(created_at=created_at))
    return book


def test_recipients_are_the_active_analysts_with_an_email(analysts):
    assert sorted(recipients()) == analysts


def test_email_of_a_day(analysts, sales):
    # The task recalculates the day itself, before writing the email
    assert tasks.send_daily_sales_email.delay(DAY.isoformat()).get() == 2

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert sorted(message.bcc) == analysts
    # Nobody in "To": the analysts don't see each other's addresses
    assert message.to == []
    assert message.subject == "Продажі за 18.11.2026: 1\xa0400,00 грн"
    assert "Замовлення: 2 (+100,0%)" in message.body
    # Plain text: the title is not HTML-escaped
    assert "1. Kobzar & Co — 4 прим., 1\xa0400,00 грн" in message.body
    assert "http://localhost:8010/?from=2026-11-18&to=2026-11-18" in message.body


def test_email_has_the_csv_of_books_and_formats(analysts, sales):
    rebuild_days([DAY])

    send_daily_sales_email(DAY)

    names = [name for name, _content, _type in mail.outbox[-1].attachments]
    assert names == ["books_2026-11-18.csv", "formats_2026-11-18.csv"]
    books = mail.outbox[-1].attachments[0][1]
    # Django keeps a text/csv attachment as text; the BOM for Excel stays first
    assert books.startswith("\ufeff")
    rows = list(csv.reader(io.StringIO(books.lstrip("\ufeff"))))
    assert rows[0] == ["Назва", "Автор", "Примірники", "Виручка, грн"]
    assert rows[1] == ["Kobzar & Co", "Author", "4", "1400.00"]


def test_a_day_without_orders_is_still_reported(analysts):
    send_daily_sales_email(DAY)

    body = mail.outbox[0].body
    assert "Замовлення: 0 (—)" in body
    assert "За цей період продажів немає." in body


def test_no_analysts_no_email():
    assert send_daily_sales_email(DAY) == 0
    assert mail.outbox == []


def test_task_sends_yesterday_by_default(analysts):
    with mock.patch.object(tasks, "today", return_value=DAY + timedelta(days=1)):
        tasks.send_daily_sales_email.delay()

    assert "18.11.2026" in mail.outbox[0].subject


def test_mail_server_error_asks_celery_for_a_retry(analysts):
    """An SMTP error (an OSError) is not a failure of the task: autoretry_for
    asks Celery to run it again later (1, 2, 4 minutes; eager mode in the
    tests raises Retry instead of waiting)."""
    error = smtplib.SMTPServerDisconnected("Connection unexpectedly closed")

    with mock.patch.object(mail.EmailMessage, "send", side_effect=error):
        with pytest.raises(Retry):
            tasks.send_daily_sales_email.delay(DAY.isoformat())

    assert tasks.send_daily_sales_email.max_retries == 3


def test_other_errors_are_not_retried(analysts):
    with mock.patch("reports.tasks.send_email", side_effect=ValueError("a bug")):
        with pytest.raises(ValueError):
            tasks.send_daily_sales_email.delay(DAY.isoformat())

"""events/processing.py: an event -> the journal and the facts, exactly once."""

from datetime import timedelta
from decimal import Decimal

import pytest

from catalog.models import Book, Category
from events.models import Event
from events.processing import InvalidEvent, Outcome, process_message
from sales.models import Order, OrderLine

from ..events_data import BASE_TIME, as_body, make_event

pytestmark = pytest.mark.django_db


# Generated with AI
def test_order_created_fills_the_facts_and_the_journal():
    event = make_event("order.created", order_id=42)

    assert process_message(as_body(event)) is Outcome.PROCESSED

    order = Order.objects.get(source_id=42)
    assert order.status == "new"
    assert order.total_uah == Decimal("700.00")
    assert order.created_at == BASE_TIME
    assert order.paid_at is None
    [line] = order.lines.all()
    assert (line.format_type, line.quantity, line.amount_uah) == ("paper", 2, Decimal("700.00"))
    assert line.book.title == "Test book"
    assert list(line.book.categories.values_list("name", flat=True)) == ["Test category"]

    journal = Event.objects.get(event_id=event["event_id"])
    assert journal.status == Event.Status.PROCESSED
    assert journal.type == "order.created"
    assert journal.processed_at is not None
    assert journal.payload["order"]["id"] == 42


# Generated with AI
def test_the_same_event_twice_changes_nothing():
    body = as_body(make_event())
    process_message(body)

    assert process_message(body) is Outcome.DUPLICATE
    assert Event.objects.count() == 1
    assert OrderLine.objects.count() == 1


# Generated with AI
def test_paid_sets_the_moment_and_the_new_status():
    process_message(as_body(make_event("order.created")))
    process_message(as_body(make_event("order.paid", minutes=5)))

    order = Order.objects.get()
    assert (order.status, order.payment_status) == ("processing", "paid")
    assert order.paid_at == BASE_TIME + timedelta(minutes=5)


# Generated with AI
def test_paid_before_created_still_ends_right():
    process_message(as_body(make_event("order.paid", minutes=5)))
    process_message(as_body(make_event("order.created")))  # late

    order = Order.objects.get()
    assert order.payment_status == "paid"  # the older snapshot didn't win
    assert order.paid_at == BASE_TIME + timedelta(minutes=5)
    assert order.last_event_at == BASE_TIME + timedelta(minutes=5)
    assert Event.objects.filter(status=Event.Status.PROCESSED).count() == 2


# Generated with AI
def test_late_paid_after_cancelled_keeps_cancelled_but_records_the_payment():
    process_message(as_body(make_event("order.cancelled", minutes=10)))
    process_message(as_body(make_event("order.paid", minutes=5)))

    order = Order.objects.get()
    assert order.status == "cancelled"
    assert order.cancelled_at == BASE_TIME + timedelta(minutes=10)
    assert order.paid_at == BASE_TIME + timedelta(minutes=5)


# Generated with AI
def test_a_newer_snapshot_replaces_the_lines_and_updates_the_book():
    process_message(as_body(make_event()))
    newer = make_event("order.paid", minutes=1)
    newer["order"]["items"][0]["quantity"] = 3
    newer["order"]["items"][0]["book"]["title"] = "Renamed book"
    newer["order"]["items"][0]["book"]["categories"] = [{"id": 2, "name": "Poetry"}]

    process_message(as_body(newer))

    [line] = OrderLine.objects.all()
    assert line.quantity == 3
    book = Book.objects.get()
    assert book.title == "Renamed book"
    assert list(book.categories.values_list("name", flat=True)) == ["Poetry"]
    assert Category.objects.count() == 2  # the old category stays for old reports


# Generated with AI
def test_broken_event_is_journaled_as_failed_without_payload():
    event = make_event()
    event["order"]["full_name"] = "Private Person"
    event["order"]["items"] = []

    with pytest.raises(InvalidEvent):
        process_message(as_body(event))

    journal = Event.objects.get(event_id=event["event_id"])
    assert journal.status == Event.Status.FAILED
    assert "items" in journal.error
    assert journal.payload == {}  # nothing of the broken body is kept
    assert not Order.objects.exists()


# Generated with AI
def test_failed_event_replayed_after_a_fix_becomes_processed():
    event = make_event()
    broken = dict(event, version=2)
    with pytest.raises(InvalidEvent):
        process_message(as_body(broken))

    assert process_message(as_body(event)) is Outcome.PROCESSED
    journal = Event.objects.get(event_id=event["event_id"])
    assert (journal.status, journal.error) == (Event.Status.PROCESSED, "")


# Generated with AI
def test_broken_copy_of_a_processed_event_doesnt_spoil_the_journal():
    event = make_event()
    process_message(as_body(event))

    with pytest.raises(InvalidEvent):
        process_message(as_body(dict(event, version=2)))

    assert Event.objects.get().status == Event.Status.PROCESSED


# Generated with AI
@pytest.mark.parametrize("body", [b"not json", b"[1, 2]", b"\xff\xfe", b'{"event_id": "x"}'])
def test_garbage_is_invalid_and_leaves_no_journal_row(body):
    with pytest.raises(InvalidEvent):
        process_message(body)

    assert not Event.objects.exists()

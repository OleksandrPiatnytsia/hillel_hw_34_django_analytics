"""The commands: publish_test_event, replay_dead_letters, consume_events."""

import json
import signal

import pytest
from django.core.management import call_command

from events.management.commands import consume_events
from events.management.commands.replay_dead_letters import clean_headers, original_routing_key
from events.topology import connect, dead_letter_exchange, dead_letter_queue, events_queue

from ..events_data import make_event

pytestmark = pytest.mark.django_db


def queue_messages(queue_factory):
    """Take every message out of a queue: their bodies as dicts."""
    bodies = []
    with connect() as connection:
        queue = queue_factory()(connection.default_channel)
        while (message := queue.get(no_ack=True)) is not None:
            bodies.append(json.loads(message.body))
    return bodies


def put_dead_letter(event, routing_key="order.paid"):
    with connect() as connection:
        connection.Producer().publish(
            json.dumps(event),
            exchange=dead_letter_exchange(),
            routing_key=routing_key,
            content_type="application/json",
            message_id=event["event_id"],
            headers={"x-death": [{"routing-keys": [routing_key]}], "x-first-death-queue": "q"},
        )


# Generated with AI
def test_publish_test_event_follows_the_contract(purged_queues, capsys):
    call_command("publish_test_event", "--type", "order.cancelled", "--order-id", "5")

    [event] = queue_messages(events_queue)
    assert event["type"] == "order.cancelled"
    assert event["order"]["id"] == 5
    assert event["order"]["status"] == "cancelled"
    assert "Published order.cancelled" in capsys.readouterr().out


# Generated with AI
def test_publish_test_event_can_reuse_an_id_and_break_the_contract(purged_queues):
    event_id = "5b0e1c8e-8a4e-4c2a-9a35-1f9c2d0e7b11"
    call_command("publish_test_event", "--event-id", event_id, "--broken")

    [event] = queue_messages(events_queue)
    assert event["event_id"] == event_id
    assert "order" not in event


# Generated with AI
def test_replay_dry_run_only_lists(purged_queues, capsys):
    put_dead_letter(make_event("order.paid"))

    call_command("replay_dead_letters", "--dry-run")

    assert "Would move 1 message(s)" in capsys.readouterr().out
    assert len(queue_messages(dead_letter_queue)) == 1  # still there
    assert queue_messages(events_queue) == []


# Generated with AI
def test_replay_moves_the_dead_letters_back(purged_queues, capsys):
    first, second = make_event("order.paid"), make_event("order.created", order_id=2)
    put_dead_letter(first, "order.paid")
    put_dead_letter(second, "order.created")

    call_command("replay_dead_letters", "--limit", "1")
    assert "Moved 1 message(s)" in capsys.readouterr().out

    call_command("replay_dead_letters")
    assert "Moved 1 message(s)" in capsys.readouterr().out

    moved = queue_messages(events_queue)
    assert [event["event_id"] for event in moved] == [first["event_id"], second["event_id"]]
    assert queue_messages(dead_letter_queue) == []


# Generated with AI
def test_dead_letter_helpers():
    class Message:
        headers = {"x-death": [{"routing-keys": ["order.paid"]}], "trace": "1"}
        delivery_info = {"routing_key": "ignored"}

    assert original_routing_key(Message()) == "order.paid"
    assert clean_headers(Message.headers) == {"trace": "1"}

    Message.headers = None
    assert original_routing_key(Message()) == "ignored"


# Generated with AI
def test_consume_events_stops_cleanly_on_sigterm(monkeypatch, capsys):
    def run(consumer):
        # What `docker compose stop` does to the process
        signal.raise_signal(signal.SIGTERM)
        assert consumer.should_stop is True

    previous = signal.getsignal(signal.SIGTERM)
    monkeypatch.setattr(consume_events.EventConsumer, "run", run)
    try:
        call_command("consume_events")
    finally:
        signal.signal(signal.SIGTERM, previous)

    assert "Consumer stopped" in capsys.readouterr().out


# Generated with AI
def test_consume_events_ctrl_c_is_not_an_error(monkeypatch, capsys):
    def run(consumer):
        raise KeyboardInterrupt

    previous = signal.getsignal(signal.SIGTERM)
    monkeypatch.setattr(consume_events.EventConsumer, "run", run)
    try:
        call_command("consume_events")
    finally:
        signal.signal(signal.SIGTERM, previous)

    assert "Consumer stopped" in capsys.readouterr().out

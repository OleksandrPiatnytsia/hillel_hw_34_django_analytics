"""events/consumer.py: ack / reject / requeue / wait, and a run on kombu's memory transport."""

import pytest
from django.db import OperationalError

from events import consumer as consumer_module
from events.consumer import EventConsumer
from events.models import Event
from events.topology import connect
from sales.models import Order

from ..events_data import as_body, make_event

pytestmark = pytest.mark.django_db


class FakeMessage:
    """What the consumer did with a message: "ack", "reject" or "requeue"."""

    def __init__(self, body):
        self.body = body
        self.result = None

    def ack(self):
        self.result = "ack"

    def reject(self, requeue=False):
        self.result = "requeue" if requeue else "reject"

    def requeue(self):
        self.result = "requeue"


@pytest.fixture
def consumer(tmp_path):
    sleeps = []
    consumer = EventConsumer(
        connection=None, heartbeat_file=tmp_path / "alive", sleep=sleeps.append
    )
    consumer.sleeps = sleeps
    return consumer


# Generated with AI
def test_processed_and_duplicate_messages_are_acknowledged(consumer):
    body = as_body(make_event())
    first, second = FakeMessage(body), FakeMessage(body)

    consumer.handle(first)
    consumer.handle(second)

    assert (first.result, second.result) == ("ack", "ack")
    assert Order.objects.count() == 1


# Generated with AI
def test_invalid_message_goes_to_the_dead_letters(consumer, caplog):
    message = FakeMessage(b"not json")

    consumer.handle(message)

    assert message.result == "reject"  # without requeue -> analytics.dlx
    assert "dead letter queue" in caplog.text


# Generated with AI
def test_unexpected_error_requeues_the_message(consumer, monkeypatch, caplog):
    def bug(body):
        raise ZeroDivisionError

    monkeypatch.setattr(consumer_module, "process_message", bug)
    message = FakeMessage(as_body(make_event()))

    consumer.handle(message)

    assert message.result == "requeue"  # RabbitMQ counts it (x-delivery-limit)
    assert "Event processing failed" in caplog.text


# Generated with AI
def test_database_down_waits_and_retries_the_same_message(consumer, monkeypatch):
    real_process = consumer_module.process_message
    failures = [OperationalError("connection refused")] * 3

    def flaky(body):
        if failures:
            raise failures.pop()
        return real_process(body)

    monkeypatch.setattr(consumer_module, "process_message", flaky)
    message = FakeMessage(as_body(make_event()))

    consumer.handle(message)

    assert message.result == "ack"
    assert consumer.sleeps == [1, 2, 4]  # the pauses grow
    assert Event.objects.count() == 1
    assert consumer.heartbeat_file.exists()  # alive while waiting


# Generated with AI
def test_waiting_stops_when_the_consumer_is_stopped(consumer, monkeypatch):
    def down(body):
        raise OperationalError("connection refused")

    monkeypatch.setattr(consumer_module, "process_message", down)
    consumer.should_stop = True
    message = FakeMessage(as_body(make_event()))

    consumer.handle(message)

    assert message.result == "requeue"  # not lost: back to the queue


# Generated with AI
def test_heartbeat_file_is_touched_on_every_iteration(consumer):
    consumer.on_iteration()

    assert consumer.heartbeat_file.exists()


# Generated with AI
def test_connection_error_is_logged_as_a_warning(consumer, caplog):
    consumer.on_connection_error(ConnectionRefusedError("refused"), 2)

    assert "RabbitMQ unavailable" in caplog.text


# Generated with AI
def test_end_to_end_on_the_memory_transport(tmp_path, purged_queues):
    """publish -> exchange -> analytics.events -> consumer -> database."""
    from django.core.management import call_command

    call_command("publish_test_event", "--type", "order.paid", "--order-id", "7")

    with connect() as connection:
        consumer = EventConsumer(connection, heartbeat_file=tmp_path / "alive")
        consumer.on_consume_ready(connection, None, [])
        # consume(limit=1): exactly one message, then back here
        for _ in consumer.consume(limit=1, timeout=5):
            pass

    order = Order.objects.get(source_id=7)
    assert order.payment_status == "paid"

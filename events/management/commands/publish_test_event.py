"""Publish one event in the format of docs/events.md, as the bookstore would.

For checking the consumer before the bookstore's publisher exists, and for
the demo:
    python manage.py publish_test_event                         order.created of order 1
    python manage.py publish_test_event --type order.paid --order-id 1
    python manage.py publish_test_event --event-id <uuid>       a duplicate on purpose
    python manage.py publish_test_event --broken                breaks the contract -> dead letters
"""

import hashlib
import json
import uuid
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from events.models import EventType
from events.topology import connect, events_exchange

# What the snapshot of the order looks like after each event
STATUS_AFTER = {
    EventType.ORDER_CREATED: ("new", "unpaid"),
    EventType.ORDER_PAID: ("processing", "paid"),
    EventType.ORDER_CANCELLED: ("cancelled", "unpaid"),
}


def sample_event(event_type, order_id, event_id=None):
    """An event of the contract with fixed made-up books (no real data)."""
    status, payment_status = STATUS_AFTER[event_type]
    now = timezone.now()
    price = Decimal("350.00")
    return {
        "event_id": str(event_id or uuid.uuid4()),
        "type": str(event_type),
        "version": 1,
        "occurred_at": now.isoformat(),
        "order": {
            "id": order_id,
            "status": status,
            "payment_status": payment_status,
            "created_at": now.isoformat(),
            "currency": "UAH",
            "total": str(price * 2),
            "total_uah": str(price * 2),
            # The bookstore hashes its user id with a secret salt; here a
            # hash of a made-up user
            "customer_key": hashlib.sha256(f"test-user-{order_id}".encode()).hexdigest(),
            "items": [
                {
                    "book": {
                        "id": 1,
                        "title": "Test book",
                        "author": "Test author",
                        "publisher": "Test publisher",
                        "language": "uk",
                        "categories": [{"id": 1, "name": "Test category"}],
                    },
                    "format_type": "paper",
                    "quantity": 2,
                    "price": str(price),
                    "amount_uah": str(price * 2),
                }
            ],
        },
    }


class Command(BaseCommand):
    help = "Publish one test event to RabbitMQ (the format of docs/events.md)."

    def add_arguments(self, parser):
        parser.add_argument("--type", default=EventType.ORDER_CREATED, choices=EventType.values)
        parser.add_argument("--order-id", type=int, default=1)
        parser.add_argument("--event-id", type=uuid.UUID, help="Reuse an id: a duplicate")
        parser.add_argument(
            "--broken", action="store_true", help="Break the contract: no order in the body"
        )

    def handle(self, *args, **options):
        event = sample_event(options["type"], options["order_id"], options["event_id"])
        if options["broken"]:
            del event["order"]

        exchange = events_exchange()
        with connect() as connection:
            producer = connection.Producer()
            producer.publish(
                json.dumps(event),
                exchange=exchange,
                routing_key=event["type"],
                # The exchange is created if the bookstore hasn't done it yet
                declare=[exchange],
                content_type="application/json",
                content_encoding="utf-8",
                # Stored on disk by RabbitMQ: survives its restart
                delivery_mode="persistent",
                message_id=event["event_id"],
                # Retry the publish if the connection drops in the middle
                retry=True,
            )
        self.stdout.write(self.style.SUCCESS(f"Published {event['type']} {event['event_id']}"))

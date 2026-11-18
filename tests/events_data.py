"""Events of the contract (docs/events.md) for the tests."""

import json
import uuid
from datetime import datetime, timedelta, timezone

from events.management.commands.publish_test_event import sample_event

BASE_TIME = datetime(2026, 11, 18, 10, 0, tzinfo=timezone.utc)


def make_event(event_type="order.created", order_id=1, minutes=0, **order_changes):
    """A valid event; `minutes` after BASE_TIME; order fields can be replaced."""
    event = sample_event(event_type, order_id)
    event["occurred_at"] = (BASE_TIME + timedelta(minutes=minutes)).isoformat()
    event["order"]["created_at"] = BASE_TIME.isoformat()
    event["order"].update(order_changes)
    return event


def as_body(event):
    return json.dumps(event).encode()


def new_id():
    return str(uuid.uuid4())

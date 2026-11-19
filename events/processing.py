"""One event from the queue -> the journal and the facts, in one transaction.

    raw body (bytes) --JSON--> dict --contract--> validated event
        --transaction--> Event row + Book / Category / Order / OrderLine
                         + DirtyDay (the order's day must be recalculated)

The consumer (events/consumer.py) acknowledges the message only after this
function has returned, i.e. after the COMMIT: a crash between the two means
one more delivery, which the unique event_id turns into a no-op.
"""

import enum
import json
import logging
import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from reports.aggregation import mark_dirty
from sales.services import apply_order_event

from .contract import validate_event
from .models import Event

logger = logging.getLogger(__name__)  # "events.processing"


class Outcome(enum.Enum):
    PROCESSED = "processed"
    # The same event_id was processed before: nothing changed
    DUPLICATE = "duplicate"


class InvalidEvent(Exception):
    """The message breaks the contract: no retry can fix it.

    The consumer sends it to the dead letter queue at once. After a fix (of
    the bookstore or of this contract) the command replay_dead_letters
    brings it back.
    """


def parse_body(body):
    """bytes -> dict, or InvalidEvent."""
    try:
        data = json.loads(body)
    except (TypeError, ValueError) as error:  # UnicodeDecodeError is a ValueError
        raise InvalidEvent(f"Not JSON: {error}") from error
    if not isinstance(data, dict):
        raise InvalidEvent("The body is not a JSON object")
    return data


def readable_event_id(data):
    """The event_id of a broken event, if it is at least a valid UUID."""
    try:
        return uuid.UUID(str(data.get("event_id")))
    except (TypeError, ValueError, AttributeError):
        return None


def record_failure(data, error):
    """Write the failed event to the journal, if it has a usable event_id.

    Without an event_id there is no row to write (the id is the key of the
    journal); the log line and the message in the dead letter queue remain.
    No payload: a broken event may carry anything, personal data included.
    """
    event_id = readable_event_id(data)
    if event_id is None:
        return
    # A processed event is never turned into a failed one (a broken copy of
    # an event that already worked)
    if Event.objects.filter(event_id=event_id, status=Event.Status.PROCESSED).exists():
        return
    event_type = data.get("type")
    Event.objects.update_or_create(
        event_id=event_id,
        defaults={
            "type": event_type[:30] if isinstance(event_type, str) else "",
            "status": Event.Status.FAILED,
            "error": error,
        },
    )


def process_message(body):
    """Process one raw message. Returns an Outcome or raises InvalidEvent.

    Any other exception (the database is down, a bug) goes up to the
    consumer, which retries; nothing is half-written thanks to the transaction.
    """
    data = parse_body(body)
    try:
        event = validate_event(data)
    except serializers.ValidationError as error:
        message = json.dumps(error.detail, ensure_ascii=False, default=str)
        record_failure(data, message)
        raise InvalidEvent(message) from error
    return process_event(event)


def process_event(event):
    """Apply a validated event exactly once. Returns an Outcome."""
    with transaction.atomic():
        # select_for_update: a second consumer with the same event waits
        # here until this transaction ends, then sees PROCESSED
        journal = Event.objects.select_for_update().filter(event_id=event["event_id"]).first()
        if journal is not None and journal.status == Event.Status.PROCESSED:
            logger.info("Duplicate event skipped: %s %s", event["type"], event["event_id"])
            return Outcome.DUPLICATE

        order = apply_order_event(event["type"], event["occurred_at"], event["order"])
        # The totals of the order's day are out of date now; the periodic
        # task recalculates the day (reports/tasks.py). In this transaction:
        # no mark without the change, no change without the mark.
        mark_dirty(order.created_at)

        # A FAILED row (an older broken copy, replayed after a fix) becomes
        # PROCESSED; otherwise a new row
        Event.objects.update_or_create(
            event_id=event["event_id"],
            defaults={
                "type": event["type"],
                "occurred_at": event["occurred_at"],
                "payload": event,
                "status": Event.Status.PROCESSED,
                "error": "",
                "processed_at": timezone.now(),
            },
        )
    logger.info(
        "Event processed: %s %s order=%s", event["type"], event["event_id"], order.source_id
    )
    return Outcome.PROCESSED

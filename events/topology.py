"""The exchanges and queues of the events in RabbitMQ (docs/events.md).

    bookstore (producer)
        |  routing key = event type: order.created / order.paid / order.cancelled
        v
    exchange "bookstore.events" (topic, durable)
        |  binding "order.*"
        v
    queue "analytics.events" (quorum, durable) --> consumer (events/consumer.py)
        |  rejected without requeue (a broken event), or delivered
        |  EVENTS_DELIVERY_LIMIT times without an ack (a bug)
        v
    exchange "analytics.dlx" (fanout) --> queue "analytics.events.dead" (classic)

Both sides declare the exchange: whoever starts first creates it, the other
one finds it (a declare with the same arguments is a no-op). The queues
belong to Analytics: the consumer declares them at start.

Quorum queue, not a classic one: it is replicated on a cluster, and it
counts the deliveries of every message itself (x-delivery-limit), so a
message that crashes the consumer can't block the queue forever.
"""

from django.conf import settings
from kombu import Exchange, Queue


def events_exchange():
    return Exchange(settings.EVENTS_EXCHANGE, type="topic", durable=True)


def dead_letter_exchange():
    # fanout: every dead message goes to the one dead letter queue, whatever
    # its routing key (the key itself is kept on the message)
    return Exchange(settings.EVENTS_DEAD_LETTER_EXCHANGE, type="fanout", durable=True)


def events_queue():
    return Queue(
        settings.EVENTS_QUEUE,
        exchange=events_exchange(),
        routing_key=settings.EVENTS_ROUTING_KEY,
        durable=True,
        queue_arguments={
            "x-queue-type": "quorum",
            "x-delivery-limit": settings.EVENTS_DELIVERY_LIMIT,
            "x-dead-letter-exchange": settings.EVENTS_DEAD_LETTER_EXCHANGE,
        },
    )


def dead_letter_queue():
    # A classic queue on purpose: quorum queues of RabbitMQ 4 have a default
    # delivery limit (20) and would DROP a dead message that was looked at
    # (replay_dead_letters --dry-run) too many times
    return Queue(settings.EVENTS_DEAD_LETTER_QUEUE, exchange=dead_letter_exchange(), durable=True)


def declare_topology(channel):
    """Create everything above (no-op for what already exists)."""
    events_queue()(channel).declare()
    dead_letter_queue()(channel).declare()


def connect():
    """A kombu connection to RabbitMQ (memory:// in the tests).

    confirm_publish: every publish waits for RabbitMQ's "stored" answer
    (publisher confirms), so publish() returns only for a message that is
    really in the queue. Used by our commands; the bookstore does the same.
    """
    from kombu import Connection

    return Connection(settings.RABBITMQ_URL, transport_options={"confirm_publish": True})

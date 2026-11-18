"""Move the messages from the dead letter queue back to the events queue.

When: after the cause is fixed (a bug in the consumer, a contract change).
    python manage.py replay_dead_letters --dry-run   only show them
    python manage.py replay_dead_letters             move all of them
    python manage.py replay_dead_letters --limit 10  move the first 10

Published to the events exchange with the routing key they had, so they
reach analytics.events again as new messages (a new delivery counter).
A message that is still broken simply comes back to the dead letter queue;
an event processed in the meantime is skipped as a duplicate (event_id).
"""

from django.core.management.base import BaseCommand

from events.topology import connect, declare_topology, dead_letter_queue, events_exchange

# Headers RabbitMQ adds when it dead-letters a message: not copied, the
# replayed message starts with a clean history
DEATH_HEADERS = ("x-death", "x-first-death-", "x-last-death-", "x-delivery-count")


def clean_headers(headers):
    return {
        name: value for name, value in (headers or {}).items() if not name.startswith(DEATH_HEADERS)
    }


def original_routing_key(message):
    """The routing key the message had before it died (x-death keeps it)."""
    deaths = (message.headers or {}).get("x-death") or []
    if deaths and deaths[0].get("routing-keys"):
        return deaths[0]["routing-keys"][0]
    return message.delivery_info.get("routing_key", "")


class Command(BaseCommand):
    help = "Move the dead letter messages back to the events queue."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only list the messages")
        parser.add_argument("--limit", type=int, default=None, help="At most this many")

    def handle(self, *args, **options):
        dry_run, limit = options["dry_run"], options["limit"]
        moved, seen = 0, []
        with connect() as connection:
            channel = connection.default_channel
            declare_topology(channel)
            queue = dead_letter_queue()(channel)
            producer = connection.Producer()
            exchange = events_exchange()

            while limit is None or len(seen) < limit:
                # get(): one message or None when the queue is empty. Not
                # acknowledged yet: a crash here leaves it in the queue.
                message = queue.get(no_ack=False)
                if message is None:
                    break
                seen.append(message)
                routing_key = original_routing_key(message)
                self.stdout.write(f"{routing_key} {message.properties.get('message_id', '?')}")
                if dry_run:
                    # Kept unacknowledged until the end, so the loop doesn't
                    # get the same message again
                    continue
                producer.publish(
                    message.body,
                    exchange=exchange,
                    routing_key=routing_key,
                    content_type=message.content_type,
                    content_encoding=message.content_encoding,
                    delivery_mode="persistent",
                    message_id=message.properties.get("message_id"),
                    headers=clean_headers(message.headers),
                    retry=True,
                )
                # Removed from the dead letters only after the publish
                message.ack()
                moved += 1

            if dry_run:
                for message in seen:
                    message.requeue()

        verb = "Would move" if dry_run else "Moved"
        count = len(seen) if dry_run else moved
        self.stdout.write(self.style.SUCCESS(f"{verb} {count} message(s)"))

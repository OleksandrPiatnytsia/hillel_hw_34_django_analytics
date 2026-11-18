import signal

from django.core.management.base import BaseCommand

from events.consumer import EventConsumer
from events.topology import connect


class Command(BaseCommand):
    help = "Read the bookstore events from RabbitMQ until stopped (Ctrl+C / SIGTERM)."

    def handle(self, *args, **options):
        with connect() as connection:
            consumer = EventConsumer(connection)

            def stop(signum, frame):
                # `docker compose stop` sends SIGTERM. Without a handler
                # Python dies at once, maybe in the middle of a message (it
                # would only be delivered again, but the log would show a
                # crash). With it the current message is finished first.
                consumer.should_stop = True

            signal.signal(signal.SIGTERM, stop)
            try:
                # run() loops: consume, reconnect after a RabbitMQ failure,
                # until should_stop
                consumer.run()
            except KeyboardInterrupt:
                pass  # Ctrl+C in a terminal: a normal stop, no traceback
        self.stdout.write("Consumer stopped")

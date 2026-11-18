"""The consumer of the bookstore events: RabbitMQ -> events.processing.

Started by `python manage.py consume_events` (service "consumer" in
docker-compose.yml). One message at a time (prefetch 1): the events of an
order are applied in the order they arrive.

What happens to a message:

    processed / duplicate      -> ack (after the COMMIT)
    breaks the contract        -> reject without requeue -> dead letter queue
    the database is down       -> wait and try the SAME message again
                                  (1, 2, 4 ... 60 s); no ack, no reject, so
                                  the delivery counter of RabbitMQ doesn't grow
    any other error (a bug)    -> requeue; after EVENTS_DELIVERY_LIMIT
                                  deliveries RabbitMQ moves it to the dead
                                  letter queue itself
    RabbitMQ is down           -> kombu (ConsumerMixin) reconnects by itself
"""

import logging
import time
from pathlib import Path

from django.conf import settings
from django.db import InterfaceError, OperationalError, close_old_connections, connection
from kombu.mixins import ConsumerMixin

from .processing import InvalidEvent, process_message
from .topology import declare_topology, events_queue

logger = logging.getLogger(__name__)  # "events.consumer"

# Pauses between the attempts while the database is down, in seconds; the
# last one repeats until the database is back
DATABASE_RETRY_DELAYS = (1, 2, 4, 8, 16, 30, 60)


class EventConsumer(ConsumerMixin):
    def __init__(self, connection, heartbeat_file=None, sleep=time.sleep):
        # ConsumerMixin expects the connection in self.connection
        self.connection = connection
        self.heartbeat_file = Path(heartbeat_file or settings.CONSUMER_HEARTBEAT_FILE)
        # Replaced in the tests: no real waiting
        self.sleep = sleep

    # --- ConsumerMixin hooks ---------------------------------------------

    def get_consumers(self, Consumer, channel):
        # Called after every (re)connection: the queues are declared again,
        # so a RabbitMQ that lost them (a new container) gets them back
        declare_topology(channel)
        # on_message (not callbacks): the raw body, our own JSON parsing,
        # no "accept" list of serializers to keep in sync
        consumer = Consumer(queues=[events_queue()], on_message=self.handle, prefetch_count=1)
        return [consumer]

    def on_consume_ready(self, connection, channel, consumers, **kwargs):
        logger.info("Consumer ready: waiting for events in %s", settings.EVENTS_QUEUE)

    def on_connection_error(self, exc, interval):
        logger.warning("RabbitMQ unavailable (%s), next attempt in %s s", exc, interval)

    def on_iteration(self):
        # About once a second while connected: the healthcheck of the
        # container reads the age of this file
        self.heartbeat_file.touch()

    # --- one message ------------------------------------------------------

    def handle(self, message):
        try:
            outcome = self.process_with_database_retry(message.body)
        except InvalidEvent as error:
            logger.error("Invalid event sent to the dead letter queue: %s", error)
            message.reject(requeue=False)
            return
        except Exception:
            # A bug or something unexpected: Sentry gets it from this ERROR
            logger.exception("Event processing failed, the message goes back to the queue")
            message.requeue()
            return
        logger.debug("Message acknowledged: %s", outcome.value)
        message.ack()

    def process_with_database_retry(self, body):
        attempt = 0
        while True:
            # A connection broken by a database restart is dropped here,
            # Django opens a new one for the next query. Not inside an outer
            # transaction (the tests run every test in one): Django closes
            # any connection whose autocommit differs from the settings, and
            # the outer transaction would be cut off.
            if not connection.in_atomic_block:
                close_old_connections()
            try:
                return process_message(body)
            except (OperationalError, InterfaceError) as error:
                if self.should_stop:
                    raise
                delay = DATABASE_RETRY_DELAYS[min(attempt, len(DATABASE_RETRY_DELAYS) - 1)]
                logger.warning("Database unavailable (%s), retry in %s s", error, delay)
                attempt += 1
                self.sleep(delay)
                # Still alive, only waiting: the healthcheck must not kill us
                self.heartbeat_file.touch()

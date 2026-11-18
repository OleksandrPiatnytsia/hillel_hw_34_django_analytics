"""The journal of every event that came from the bookstore."""

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils.translation import gettext_lazy as _


class EventType(models.TextChoices):
    """The routing keys of the events (docs/events.md)."""

    ORDER_CREATED = "order.created", _("Order created")
    ORDER_PAID = "order.paid", _("Order paid")
    ORDER_CANCELLED = "order.cancelled", _("Order cancelled")


class Event(models.Model):
    """One event, stored in the same transaction as its effect on the facts.

    event_id is unique: this is the idempotency of the consumer. RabbitMQ
    delivers "at least once", and the bookstore's outbox may send an event
    again after a lost confirmation; the second copy finds its row here and
    changes nothing.
    The journal is also the audit (what came, when, what failed) and the
    source to rebuild the facts from: the payload is the validated event,
    with only the fields of the contract (nothing personal can slip in).
    """

    class Status(models.TextChoices):
        PROCESSED = "processed", _("Processed")
        FAILED = "failed", _("Failed")

    event_id = models.UUIDField(_("event id"), unique=True)
    # Empty only for a failed event whose type couldn't be read
    type = models.CharField(_("type"), max_length=30, choices=EventType.choices, blank=True)
    # When it happened in the bookstore; empty only for a failed event
    occurred_at = models.DateTimeField(_("occurred at"), null=True, blank=True)
    received_at = models.DateTimeField(_("received at"), auto_now_add=True, db_index=True)
    # DjangoJSONEncoder: the validated data has Decimal, datetime and UUID
    # values, the plain JSON encoder can't write them
    payload = models.JSONField(_("payload"), default=dict, blank=True, encoder=DjangoJSONEncoder)
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, db_index=True)
    # Why it failed: the contract errors (the message itself is in the dead
    # letter queue, see docs/events.md)
    error = models.TextField(_("error"), blank=True)
    processed_at = models.DateTimeField(_("processed at"), null=True, blank=True)

    class Meta:
        verbose_name = _("event")
        verbose_name_plural = _("events")
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.type or '?'} {self.event_id}"

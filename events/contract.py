"""The contract of the events (docs/events.md), checked with DRF serializers.

A serializer is used here only as a validator: it checks the types and the
allowed values, turns the strings into Decimal / datetime / UUID, and keeps
ONLY the declared fields. A field that is not in the contract (a name or a
phone sent by mistake) never reaches the database.
"""

from rest_framework import serializers

from sales.models import Order, OrderLine

from .models import EventType

# The version of the body this code understands. A breaking change of the
# contract gets a new number; old consumers then send the new events to the
# dead letter queue instead of reading them wrong.
SUPPORTED_VERSIONS = [1]


class CategorySnapshotSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=100)


class BookSnapshotSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    title = serializers.CharField(max_length=255)
    author = serializers.CharField(max_length=255, allow_blank=True)
    publisher = serializers.CharField(max_length=255, allow_blank=True)
    language = serializers.CharField(max_length=2, allow_blank=True)
    categories = CategorySnapshotSerializer(many=True)


class OrderItemSnapshotSerializer(serializers.Serializer):
    book = BookSnapshotSerializer()
    format_type = serializers.ChoiceField(choices=OrderLine.FormatType.choices)
    quantity = serializers.IntegerField(min_value=1)
    price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    amount_uah = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)


class OrderSnapshotSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    status = serializers.ChoiceField(choices=Order.Status.choices)
    payment_status = serializers.ChoiceField(choices=Order.PaymentStatus.choices)
    created_at = serializers.DateTimeField()
    currency = serializers.CharField(min_length=3, max_length=3)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    total_uah = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    customer_key = serializers.RegexField(r"^[0-9a-f]{64}$")
    items = OrderItemSnapshotSerializer(many=True, allow_empty=False)


class EventSerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    type = serializers.ChoiceField(choices=EventType.choices)
    version = serializers.ChoiceField(choices=SUPPORTED_VERSIONS)
    occurred_at = serializers.DateTimeField()
    order = OrderSnapshotSerializer()


def validate_event(data):
    """The validated event, or serializers.ValidationError with every problem."""
    serializer = EventSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data

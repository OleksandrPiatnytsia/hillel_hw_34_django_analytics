"""events/contract.py: what the consumer accepts."""

import uuid
from decimal import Decimal

import pytest
from rest_framework import serializers

from events.contract import validate_event

from ..events_data import make_event


# Generated with AI
def test_valid_event_is_converted_to_python_types():
    event = validate_event(make_event("order.paid"))

    assert isinstance(event["event_id"], uuid.UUID)
    assert event["order"]["total"] == Decimal("700.00")
    assert event["occurred_at"].tzinfo is not None
    assert event["order"]["items"][0]["book"]["categories"][0]["name"] == "Test category"


# Generated with AI
def test_fields_outside_the_contract_are_dropped():
    data = make_event()
    data["order"]["full_name"] = "Taras Shevchenko"
    data["order"]["phone"] = "+380000000000"
    data["order"]["items"][0]["book"]["isbn"] = "123"

    event = validate_event(data)

    assert "full_name" not in event["order"]
    assert "phone" not in event["order"]
    assert "isbn" not in event["order"]["items"][0]["book"]


# Generated with AI
@pytest.mark.parametrize(
    "change",
    [
        lambda event: event.update(type="order.shipped"),
        lambda event: event.update(version=2),
        lambda event: event.update(event_id="not-a-uuid"),
        lambda event: event.pop("occurred_at"),
        lambda event: event["order"].update(items=[]),
        lambda event: event["order"].update(customer_key="ann@example.com"),
        lambda event: event["order"].update(total="-1.00"),
        lambda event: event["order"]["items"][0].update(format_type="vinyl"),
        lambda event: event["order"]["items"][0].update(quantity=0),
    ],
)
def test_broken_events_are_refused(change):
    event = make_event()
    change(event)

    with pytest.raises(serializers.ValidationError):
        validate_event(event)

from catalog.services import upsert_book
from events.models import EventType

from .models import Order, OrderLine

# The moment field of Order each event type fills
MOMENT_FIELDS = {
    EventType.ORDER_PAID: "paid_at",
    EventType.ORDER_CANCELLED: "cancelled_at",
}


def apply_order_event(event_type, occurred_at, snapshot):
    """Bring the order up to date with one event. Returns the Order.

    Every event carries the WHOLE order (the snapshot), so the events may
    come in any order:
    - order.paid before order.created: the order is created from the paid
      snapshot, the late order.created then changes nothing;
    - an older snapshot after a newer one (a retry of the bookstore): the
      fields stay as the newer one set them (last_event_at).
    The moments (paid_at, cancelled_at) are facts of their own and are set
    even from an older event: the order WAS paid at that moment.
    Runs inside the transaction of events.processing.process_event.
    """
    order = Order.objects.select_for_update().filter(source_id=snapshot["id"]).first()
    is_newer = order is None or occurred_at >= order.last_event_at

    if order is None:
        order = Order(source_id=snapshot["id"])

    if is_newer:
        order.status = snapshot["status"]
        order.payment_status = snapshot["payment_status"]
        order.created_at = snapshot["created_at"]
        order.currency = snapshot["currency"]
        order.total = snapshot["total"]
        order.total_uah = snapshot["total_uah"]
        order.customer_key = snapshot["customer_key"]
        order.last_event_at = occurred_at

    moment_field = MOMENT_FIELDS.get(event_type)
    if moment_field and getattr(order, moment_field) is None:
        setattr(order, moment_field, occurred_at)

    order.save()

    if is_newer:
        # The lines of the snapshot replace the old ones: simpler and safer
        # than matching them one by one, and an order has only a few lines
        order.lines.all().delete()
        OrderLine.objects.bulk_create(
            OrderLine(
                order=order,
                book=upsert_book(item["book"]),
                format_type=item["format_type"],
                quantity=item["quantity"],
                price=item["price"],
                amount_uah=item["amount_uah"],
            )
            for item in snapshot["items"]
        )
    return order

"""The read-only admin pages of the data that comes from the events."""

import pytest

from events.processing import process_message
from sales.models import Order

from ..events_data import as_body, make_event

pytestmark = pytest.mark.django_db


# Generated with AI
@pytest.mark.parametrize(
    "path",
    [
        "/admin/events/event/",
        "/admin/sales/order/",
        "/admin/catalog/book/",
        "/admin/catalog/category/",
    ],
)
def test_lists_open_and_have_no_add_button(admin_client, path):
    process_message(as_body(make_event()))

    response = admin_client.get(path)

    assert response.status_code == 200
    assert f"{path}add/" not in response.content.decode()  # no "Add" for this model


# Generated with AI
def test_order_page_shows_its_lines_read_only(admin_client):
    process_message(as_body(make_event()))
    order = Order.objects.get()
    response = admin_client.get(f"/admin/sales/order/{order.pk}/change/")

    assert response.status_code == 200
    assert "Test book" in response.content.decode()

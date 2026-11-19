"""Model factories (factory-boy): test objects with valid data in one line.

UserFactory()                       a user with a unique username
UserFactory(username="ann")         any field can be given
OrderLineFactory(order__status="cancelled")   fields of the related order too
"""

from datetime import datetime
from datetime import timezone as dt_timezone
from decimal import Decimal

import factory

from catalog.models import Book, Category
from sales.models import Order, OrderLine
from users.models import User

# The password of every factory user, for the tests that log in with a form
PASSWORD = "test-password-123"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda number: f"user{number}")
    email = factory.LazyAttribute(lambda user: f"{user.username}@example.com")
    password = PASSWORD

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        # create_user() hashes the password, as a real sign-up would;
        # the default create() would store the plain text
        return model_class.objects.create_user(*args, **kwargs)


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category

    source_id = factory.Sequence(lambda number: number + 1)
    name = factory.Sequence(lambda number: f"Category {number}")


class BookFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Book

    source_id = factory.Sequence(lambda number: number + 1)
    title = factory.Sequence(lambda number: f"Book {number}")
    author = "Author"
    publisher = "Publisher"
    language = "uk"


class OrderFactory(factory.django.DjangoModelFactory):
    """An order as the consumer would store it; customer_key = a fake hash."""

    class Meta:
        model = Order

    source_id = factory.Sequence(lambda number: number + 1)
    status = Order.Status.NEW
    payment_status = Order.PaymentStatus.UNPAID
    created_at = datetime(2026, 11, 18, 10, 0, tzinfo=dt_timezone.utc)
    currency = "UAH"
    total = Decimal("700.00")
    total_uah = factory.SelfAttribute("total")
    customer_key = factory.Sequence(lambda number: f"{number:064x}")
    last_event_at = factory.SelfAttribute("created_at")


class OrderLineFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OrderLine

    order = factory.SubFactory(OrderFactory)
    book = factory.SubFactory(BookFactory)
    format_type = OrderLine.FormatType.PAPER
    quantity = 2
    price = Decimal("350.00")
    amount_uah = factory.LazyAttribute(lambda line: line.price * line.quantity)

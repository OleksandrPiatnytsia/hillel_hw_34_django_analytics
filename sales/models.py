"""Orders of the bookstore, as the events describe them.

Filled only by the consumer (sales/services.py) from the order snapshots.
No personal data: no names, phones, addresses or emails. The buyer is
customer_key, a hash the bookstore makes from its user id: enough to tell
new customers from returning ones, useless for finding the person.
All the money in UAH comes ready from the bookstore (it knows the NBU rate
of the moment of the order).
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from catalog.models import Book


class Order(models.Model):
    # The values of the bookstore (orders.Order.Status / PaymentStatus)
    class Status(models.TextChoices):
        NEW = "new", _("New")
        PROCESSING = "processing", _("Processing")
        SHIPPED = "shipped", _("Shipped")
        COMPLETED = "completed", _("Completed")
        CANCELLED = "cancelled", _("Cancelled")

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", _("Unpaid")
        PARTIALLY_PAID = "partially_paid", _("Partially paid")
        PAID = "paid", _("Paid")

    source_id = models.PositiveIntegerField(_("id in the bookstore"), unique=True)
    status = models.CharField(_("status"), max_length=20, choices=Status.choices)
    payment_status = models.CharField(
        _("payment status"), max_length=20, choices=PaymentStatus.choices
    )
    # When the order was placed in the bookstore (the day of the reports)
    created_at = models.DateTimeField(_("created at"), db_index=True)
    # The moments of the order.paid / order.cancelled events; empty = never
    paid_at = models.DateTimeField(_("paid at"), null=True, blank=True)
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)
    # The currency the customer paid in, and the total in it
    currency = models.CharField(_("currency"), max_length=3)
    total = models.DecimalField(_("total"), max_digits=12, decimal_places=2)
    total_uah = models.DecimalField(_("total, UAH"), max_digits=12, decimal_places=2)
    # sha256 hex of the bookstore's user id with a secret salt (64 characters)
    customer_key = models.CharField(_("customer key"), max_length=64, db_index=True)
    # occurred_at of the event whose snapshot is applied now. An older
    # snapshot that comes later (a retry of the bookstore's outbox) is not
    # applied over a newer one.
    last_event_at = models.DateTimeField(_("last event at"))

    class Meta:
        verbose_name = _("order")
        verbose_name_plural = _("orders")
        ordering = ["-created_at"]

    def __str__(self):
        return f"#{self.source_id}"


class OrderLine(models.Model):
    class FormatType(models.TextChoices):
        PAPER = "paper", _("Paper")
        EBOOK = "ebook", _("E-book")
        AUDIO = "audio", _("Audiobook")

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="lines", verbose_name=_("order")
    )
    # PROTECT: a book with sales must never disappear from the reports
    book = models.ForeignKey(
        Book, on_delete=models.PROTECT, related_name="order_lines", verbose_name=_("book")
    )
    format_type = models.CharField(_("format"), max_length=10, choices=FormatType.choices)
    quantity = models.PositiveIntegerField(_("quantity"))
    # The price of one copy in the currency of the order
    price = models.DecimalField(_("price"), max_digits=12, decimal_places=2)
    # The whole line (price x quantity) in UAH
    amount_uah = models.DecimalField(_("amount, UAH"), max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = _("order line")
        verbose_name_plural = _("order lines")

    def __str__(self):
        return f"{self.book} x {self.quantity}"

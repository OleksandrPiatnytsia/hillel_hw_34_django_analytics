"""Books and categories of the bookstore, as the events describe them.

Not a copy of the bookstore's catalog: only what the reports need, filled
from the order snapshots of the events (catalog/services.py). A book that
was never ordered is not here, and that is fine for sales analytics.

source_id = the id in the bookstore's database. Our own id stays separate:
the two databases number their rows independently.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Category(models.Model):
    source_id = models.PositiveIntegerField(_("id in the bookstore"), unique=True)
    name = models.CharField(_("name"), max_length=100)

    class Meta:
        verbose_name = _("category")
        verbose_name_plural = _("categories")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Book(models.Model):
    source_id = models.PositiveIntegerField(_("id in the bookstore"), unique=True)
    title = models.CharField(_("title"), max_length=255)
    # Plain text, not separate tables: the reports group by them, nobody
    # edits them here, and the bookstore stays the place where they live
    author = models.CharField(_("author"), max_length=255, blank=True)
    publisher = models.CharField(_("publisher"), max_length=255, blank=True)
    # ISO 639-1 code ("uk", "en"), as in the bookstore; may be empty there
    language = models.CharField(_("language"), max_length=2, blank=True)
    categories = models.ManyToManyField(
        Category, related_name="books", blank=True, verbose_name=_("categories")
    )
    # When the last snapshot of the book was applied
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("book")
        verbose_name_plural = _("books")
        ordering = ["title"]

    def __str__(self):
        return self.title

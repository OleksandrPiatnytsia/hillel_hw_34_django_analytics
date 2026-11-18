from django.contrib import admin

from .models import Book, Category


class ReadOnlyAdmin(admin.ModelAdmin):
    """The data comes from the events; an edit here would be overwritten by
    the next event anyway, and would make the reports lie until then."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Category)
class CategoryAdmin(ReadOnlyAdmin):
    list_display = ("name", "source_id")
    search_fields = ("name",)


@admin.register(Book)
class BookAdmin(ReadOnlyAdmin):
    list_display = ("title", "author", "publisher", "language", "source_id")
    list_filter = ("language", "categories")
    search_fields = ("title", "author")

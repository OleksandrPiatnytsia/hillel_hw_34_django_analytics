from django.contrib import admin

from catalog.admin import ReadOnlyAdmin

from .models import Order, OrderLine


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0
    can_delete = False
    fields = ("book", "format_type", "quantity", "price", "amount_uah")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(ReadOnlyAdmin):
    list_display = (
        "source_id",
        "created_at",
        "status",
        "payment_status",
        "total_uah",
        "paid_at",
        "cancelled_at",
    )
    list_filter = ("status", "payment_status", "currency")
    search_fields = ("source_id",)
    date_hierarchy = "created_at"
    inlines = [OrderLineInline]

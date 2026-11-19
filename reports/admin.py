from django.contrib import admin

from catalog.admin import ReadOnlyAdmin

from .models import DailyBookSales, DailySales, DirtyDay, ReportExport

# Read-only: the rows are computed by reports/aggregation.py, a hand edit
# would be overwritten by the next recalculation anyway


@admin.register(DailySales)
class DailySalesAdmin(ReadOnlyAdmin):
    list_display = (
        "day",
        "orders",
        "paid_orders",
        "cancelled_orders",
        "revenue_uah",
        "items_sold",
        "average_order_uah",
        "new_customers",
        "returning_customers",
        "updated_at",
    )
    date_hierarchy = "day"


@admin.register(DailyBookSales)
class DailyBookSalesAdmin(ReadOnlyAdmin):
    list_display = ("day", "book", "format_type", "quantity", "revenue_uah")
    list_filter = ("format_type",)
    list_select_related = ("book",)
    search_fields = ("book__title",)
    date_hierarchy = "day"


@admin.register(DirtyDay)
class DirtyDayAdmin(ReadOnlyAdmin):
    list_display = ("day", "marked_at")


@admin.register(ReportExport)
class ReportExportAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "user", "report", "format", "status", "size", "finished_at")
    list_filter = ("status", "format", "report")
    list_select_related = ("user",)
    # The file itself is downloaded on the page "My exports", not shown here
    exclude = ("content",)

    def has_delete_permission(self, request, obj=None):
        # A stuck or unneeded export can be removed by hand
        return request.user.is_superuser

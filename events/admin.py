from django.contrib import admin

from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    """The journal, read-only: events are written only by the consumer.
    The failed ones: filter "Status: Failed", the reason is in "error"."""

    list_display = ("received_at", "type", "status", "occurred_at", "event_id")
    list_filter = ("status", "type")
    search_fields = ("event_id",)
    date_hierarchy = "received_at"
    readonly_fields = [field.name for field in Event._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # The detail page still opens (view permission), every field read-only
        return False

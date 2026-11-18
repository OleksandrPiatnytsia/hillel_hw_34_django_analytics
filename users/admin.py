from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Django's own user admin (password change, groups, permissions),
    registered for our model: the custom User is not in the admin by itself."""

    list_display = ("username", "email", "is_staff", "is_active", "group_names")
    list_filter = ("is_staff", "is_superuser", "is_active", "groups")

    def get_queryset(self, request):
        # The groups of every row in one extra query, not one query per row
        return super().get_queryset(request).prefetch_related("groups")

    @admin.display(description="groups")
    def group_names(self, user):
        return ", ".join(group.name for group in user.groups.all()) or "-"

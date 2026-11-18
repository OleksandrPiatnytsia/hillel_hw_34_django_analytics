from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """The user of Analytics: an analyst, an admin or a service account.

    Nothing new yet, but a custom model from the very first migration: adding
    fields later is a normal migration, while switching from auth.User to a
    custom model in a project with data is a painful manual operation
    (Django docs: "Using a custom user model when starting a project").

    No customers here: the buyers of the bookstore never log in to
    Analytics, and their personal data never comes here (customer_key only).
    """

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        # Permissions that don't belong to any table: the access to the
        # pages and to the API as a whole. Given to the groups in groups.py.
        # Model permissions (view_dailysales, ...) join them at stage 4.
        permissions = [
            ("view_analytics", _("Can view the analytics dashboard and reports")),
            ("use_reports_api", _("Can read the reports through the REST API")),
        ]

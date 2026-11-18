from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "users"
    verbose_name = _("Users")

    def ready(self):
        # Connects the receivers of the login / logout signals (the
        # @receiver decorators run when the module is imported)
        from . import signals  # noqa: F401
        from .groups import create_groups

        # The groups are created after every migrate (and after the flush of
        # a test database), not in a data migration: post_migrate runs
        # after Django has created the permissions of every model, and the
        # function is safe to run again (get_or_create, set()). sender=self:
        # once per migrate, not once per installed app.
        post_migrate.connect(create_groups, sender=self, dispatch_uid="users_create_groups")

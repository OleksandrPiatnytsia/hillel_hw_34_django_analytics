"""The groups of Analytics and their permissions.

    Analysts  the people who read the numbers: the dashboard and the web
              reports (users.view_analytics)
    Services  the service accounts of other services: the bookstore reads
              the reports through the REST API with the JWT of such an
              account (users.use_reports_api)

A superuser has every permission without a group. A new user gets a group
in the admin (Users -> the user -> Groups).
"""

import logging

from django.contrib.auth.models import Group, Permission

logger = logging.getLogger(__name__)  # "users.groups"

ANALYSTS = "Analysts"
SERVICES = "Services"

# group name -> permissions as "app_label.codename"
GROUP_PERMISSIONS = {
    ANALYSTS: ["users.view_analytics"],
    SERVICES: ["users.use_reports_api"],
}


def get_permission(full_name):
    app_label, codename = full_name.split(".")
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def create_groups(sender=None, using="default", **kwargs):
    """Create the groups and give them exactly GROUP_PERMISSIONS.

    A post_migrate receiver (users/apps.py). Safe to run any number of
    times: an existing group is reused, and set() replaces its permissions
    with the list above, so the code stays the single source of truth (a
    permission removed from the list is also removed from the group).
    """
    for name, permission_names in GROUP_PERMISSIONS.items():
        group, created = Group.objects.using(using).get_or_create(name=name)
        group.permissions.set([get_permission(full_name) for full_name in permission_names])
        if created:
            logger.info("Group created: %s", name)

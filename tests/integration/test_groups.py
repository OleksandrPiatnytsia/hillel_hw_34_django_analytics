"""The groups of Analytics and their permissions (users/groups.py)."""

import pytest
from django.contrib.auth.models import Group

from users.groups import ANALYSTS, GROUP_PERMISSIONS, SERVICES, create_groups


def permission_names(group):
    return sorted(
        f"{permission.content_type.app_label}.{permission.codename}"
        for permission in group.permissions.select_related("content_type")
    )


# Generated with AI
@pytest.mark.django_db
def test_migrate_creates_the_groups_with_their_permissions():
    for name, expected in GROUP_PERMISSIONS.items():
        assert permission_names(Group.objects.get(name=name)) == sorted(expected)


# Generated with AI
@pytest.mark.django_db
def test_create_groups_is_safe_to_run_again_and_restores_the_permissions():
    analysts = Group.objects.get(name=ANALYSTS)
    analysts.permissions.clear()  # someone removed them in the admin

    create_groups()

    assert Group.objects.filter(name__in=[ANALYSTS, SERVICES]).count() == 2
    assert permission_names(analysts) == ["users.view_analytics"]


# Generated with AI
@pytest.mark.django_db
def test_group_members_get_the_permissions(analyst, service_account):
    assert analyst.has_perm("users.view_analytics")
    assert not analyst.has_perm("users.use_reports_api")
    assert service_account.has_perm("users.use_reports_api")
    assert not service_account.has_perm("users.view_analytics")


# Generated with AI
@pytest.mark.django_db
def test_admin_user_list_shows_the_groups(admin_client, analyst):
    response = admin_client.get("/admin/users/user/")

    assert response.status_code == 200
    assert ANALYSTS in response.content.decode()

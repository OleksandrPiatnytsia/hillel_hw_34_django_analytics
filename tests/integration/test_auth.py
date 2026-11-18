"""Login, logout and the access to the dashboard."""

import pytest
from django.urls import reverse

from ..factories import PASSWORD, UserFactory


# Generated with AI
@pytest.mark.django_db
def test_login_page_renders(client):
    response = client.get(reverse("users:login"))

    assert response.status_code == 200
    assert 'name="username"' in response.content.decode()


# Generated with AI
@pytest.mark.django_db
def test_login_leads_to_the_dashboard_and_is_logged(client, analyst, caplog):
    caplog.set_level("INFO", logger="users.signals")

    response = client.post(
        reverse("users:login"), {"username": analyst.username, "password": PASSWORD}, follow=True
    )

    assert response.redirect_chain[-1][0] == reverse("reports:dashboard")
    assert response.status_code == 200
    assert f"Login: user={analyst.username}" in caplog.text


# Generated with AI
@pytest.mark.django_db
def test_wrong_password_shows_an_error_and_is_logged(client, caplog):
    UserFactory(username="ann")

    response = client.post(reverse("users:login"), {"username": "ann", "password": "wrong"})

    assert response.status_code == 200  # the form again
    assert response.context["form"].errors
    assert "Failed login: username=ann" in caplog.text
    # The password never goes back into the page
    assert "wrong" not in response.content.decode()


# Generated with AI
@pytest.mark.django_db
def test_logged_in_user_skips_the_login_page(analyst_client):
    response = analyst_client.get(reverse("users:login"))

    assert response.status_code == 302


# Generated with AI
@pytest.mark.django_db
def test_logout_is_post_only(analyst_client, caplog):
    caplog.set_level("INFO", logger="users.signals")

    assert analyst_client.get(reverse("users:logout")).status_code == 405

    response = analyst_client.post(reverse("users:logout"))

    assert response.status_code == 302
    assert response.url == reverse("users:login")
    assert "Logout: user=analyst" in caplog.text


# Generated with AI
@pytest.mark.django_db
def test_anonymous_visitor_is_sent_to_login(client):
    response = client.get(reverse("reports:dashboard"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("users:login"))


# Generated with AI
@pytest.mark.django_db
def test_user_without_permission_gets_403(user_client):
    response = user_client.get(reverse("reports:dashboard"))

    assert response.status_code == 403
    assert "Analysts" in response.content.decode()  # the hint of templates/403.html


# Generated with AI
@pytest.mark.django_db
def test_analyst_sees_the_dashboard(analyst_client):
    response = analyst_client.get(reverse("reports:dashboard"))

    assert response.status_code == 200
    assert "reports/dashboard.html" in [template.name for template in response.templates]


# Generated with AI
@pytest.mark.django_db
def test_superuser_sees_the_dashboard_without_a_group(client):
    client.force_login(UserFactory(is_superuser=True, is_staff=True))

    response = client.get(reverse("reports:dashboard"))

    assert response.status_code == 200
    assert reverse("admin:index") in response.content.decode()  # the navbar link


# Generated with AI
@pytest.mark.django_db
def test_unknown_page_is_404(analyst_client):
    response = analyst_client.get("/no-such-page/")

    assert response.status_code == 404
    assert "404.html" in [template.name for template in response.templates]  # ours

from django.contrib.auth import views as auth_views
from django.contrib.messages.views import SuccessMessageMixin
from django.utils.translation import gettext_lazy as _


class UserLoginView(SuccessMessageMixin, auth_views.LoginView):
    """GET: the form; POST: login -> ?next= or LOGIN_REDIRECT_URL (the dashboard).

    No sign-up page on purpose: the accounts of Analytics are created by an
    admin, who also decides the group (Analysts / Services).
    """

    template_name = "users/login.html"
    # A logged-in user who opens /accounts/login/ goes straight on
    redirect_authenticated_user = True
    success_message = _("You are logged in.")


class UserLogoutView(auth_views.LogoutView):
    """POST only (Django 5+): a GET link could log anyone out from another site.
    The navbar has a small form with a button."""

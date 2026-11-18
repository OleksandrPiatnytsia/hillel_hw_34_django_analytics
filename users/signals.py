"""Logging of authentication events through Django's auth signals.

Signals are sent by django.contrib.auth itself, wherever the login happens:
our login page, the admin login page. One receiver here covers all of them.
The lines carry the IP address, so config/sentry.py keeps this logger out of
the Sentry breadcrumbs.
"""

import logging

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

logger = logging.getLogger(__name__)  # "users.signals"


def get_client_ip(request):
    # Behind nginx REMOTE_ADDR is still the real client: uvicorn takes it
    # from X-Forwarded-For (forwarded_allow_ips in gunicorn.conf.py).
    # request may be None, e.g. authenticate() called from a script.
    if request is None:
        return "-"
    return request.META.get("REMOTE_ADDR", "-")


@receiver(user_logged_in, dispatch_uid="users_log_login")
def log_login(sender, request, user, **kwargs):
    logger.info("Login: user=%s ip=%s", user.username, get_client_ip(request))


@receiver(user_logged_out, dispatch_uid="users_log_logout")
def log_logout(sender, request, user, **kwargs):
    # user is None if the session had already expired
    username = user.username if user else "-"
    logger.info("Logout: user=%s ip=%s", username, get_client_ip(request))


@receiver(user_login_failed, dispatch_uid="users_log_login_failed")
def log_login_failed(sender, credentials, request=None, **kwargs):
    # Only the username, never the password. Many of these in a row from one
    # IP look like password guessing.
    logger.warning(
        "Failed login: username=%s ip=%s",
        credentials.get("username", "-"),
        get_client_ip(request),
    )

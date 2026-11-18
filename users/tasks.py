import logging

from celery import shared_task
from django.core import management

logger = logging.getLogger(__name__)  # "users.tasks"


@shared_task
def clear_expired_sessions():
    """Delete the expired sessions from the django_session table.

    Sessions are cached_db (config/settings/base.py): every login leaves a
    row, and Django never deletes the expired ones by itself. Celery Beat
    runs this every night (CELERY_BEAT_SCHEDULE). Safe to run twice.
    """
    management.call_command("clearsessions")
    logger.info("Expired sessions cleared")

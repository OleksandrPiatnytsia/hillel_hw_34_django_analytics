import logging
from datetime import timedelta

from celery import shared_task

from .aggregation import claim_dirty_days, mark_days, rebuild_days
from .days import today

logger = logging.getLogger(__name__)  # "reports.tasks"


@shared_task
def refresh_reports():
    """Every 10 minutes (CELERY_BEAT_SCHEDULE): today + the marked days.

    Today always, so the dashboard is fresh even if a mark was missed; the
    marked days catch late payments, cancellations and backfilled orders of
    any older day. Safe to run twice: rebuild_day computes from scratch.
    """
    claimed = claim_dirty_days()
    try:
        return [str(day) for day in rebuild_days([*claimed, today()])]
    except Exception:
        # The marks were already taken: put them back, or those days would
        # stay wrong until somebody runs rebuild_reports by hand
        mark_days(claimed)
        logger.exception("Recalculation of the reports failed, days marked again")
        raise


@shared_task
def close_yesterday():
    """Every night: yesterday computed once more, after its last order.

    A safety net on top of the marks: yesterday is final in the reports
    even if a mark was lost (for example, an order fixed by hand in the
    database).
    """
    yesterday = today() - timedelta(days=1)
    rebuild_days([yesterday])
    return str(yesterday)

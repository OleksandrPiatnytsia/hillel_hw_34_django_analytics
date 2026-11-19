"""The daily sales email to the Analysts group (Celery beat, every morning).

    yesterday (a Kyiv day)
      -> totals of the day vs the day before (queries.summary + compare)
      -> top 10 books of the day
      -> CSV attachments: books and formats of the day, built by the same
         report classes as the exports, so the files match the web pages
      -> one email, the analysts in Bcc

It took over the sales part of the bookstore's daily email; the low-stock
part stays in the bookstore (it is about the warehouse, not sales).
"""

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation

from users.groups import ANALYSTS

from . import queries
from .exports import write_csv
from .periods import Period, compare

logger = logging.getLogger(__name__)  # "reports.emails"

TOP_BOOKS_LIMIT = 10
# The numbers of the email, each with its change against the day before
SUMMARY_KEYS = (
    "orders",
    "revenue_uah",
    "average_order_uah",
    "items_sold",
    "paid_share",
    "cancelled_share",
    "new_customers",
)


def recipients():
    """The active analysts with an email address."""
    return list(
        get_user_model()
        .objects.filter(groups__name=ANALYSTS, is_active=True)
        .exclude(email="")
        .values_list("email", flat=True)
        .distinct()
    )


def report_csv(view_class, period):
    """The CSV of a report page for a period (the same file as an export)."""
    report = view_class.for_export(period, {})
    columns, rows = report.get_table()
    return write_csv(columns, rows)


def build_context(day):
    period = Period(day, day)
    totals = queries.summary(period)
    previous = queries.summary(period.previous)
    query = urlencode(period.as_params())
    return {
        "day": day,
        "totals": totals,
        "changes": {key: compare(totals[key], previous[key]) for key in SUMMARY_KEYS},
        "top_books": queries.top_books(period, limit=TOP_BOOKS_LIMIT),
        "formats": queries.formats(period),
        "dashboard_url": f"{settings.SITE_URL}{reverse('reports:dashboard')}?{query}",
    }


def send_daily_sales_email(day):
    """Build and send the email of one day. Returns the number of recipients.

    Raises on an SMTP / API error: the Celery task retries it.
    """
    # Imported here: views imports tasks, tasks imports this module
    from .views import BooksReportView, FormatsReportView

    emails = recipients()
    if not emails:
        logger.warning("Daily sales email %s: no active analysts with an email", day)
        return 0

    period = Period(day, day)
    # One language for all: the users of Analytics have no language of their own
    with translation.override(settings.LANGUAGE_CODE):
        context = build_context(day)
        message = EmailMessage(
            subject=render_to_string("reports/emails/daily_sales_subject.txt", context).strip(),
            body=render_to_string("reports/emails/daily_sales.txt", context),
            from_email=settings.DEFAULT_FROM_EMAIL,
            # Bcc: the analysts don't see each other's addresses
            bcc=emails,
        )
        message.attach(f"books_{day}.csv", report_csv(BooksReportView, period), "text/csv")
        message.attach(f"formats_{day}.csv", report_csv(FormatsReportView, period), "text/csv")
    message.send()

    logger.info(
        "Daily sales email %s sent to %d analysts: %s orders, %s UAH",
        day,
        len(emails),
        context["totals"]["orders"],
        context["totals"]["revenue_uah"],
    )
    return len(emails)

"""The REST API of the reports: what the bookstore shows on its analytics page.

    GET /api/reports/summary/    totals of the period + of the previous one
    GET /api/reports/daily/      every day of the period
    GET /api/reports/top-books/  the best books (?limit=, 10 by default)
    GET /api/reports/formats/    paper / e-book / audio

    The period, as on the web pages (reports/periods.py):
        ?period=7|30|90            the last N days (30 without parameters)
        ?from=YYYY-MM-DD&to=YYYY-MM-DD   at most 366 days

    Bookstore (its service account in the group Services)
        POST /api/token/ -> access token (15 minutes)
        GET /api/reports/summary/?period=30  "Authorization: Bearer <access>"
        200 JSON | 400 bad period | 401 no / expired token | 403 no permission

The numbers come from reports/queries.py, the same as the web pages, and go
through the same cache of answers: it is dropped after every recalculation.
Money is a string with 2 decimals ("1234.50"): JSON numbers are floats and
would round the kopecks.
"""

import logging

from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import queries
from .cache import cached_answer
from .periods import DEFAULT_PRESET, PRESETS, PeriodError, compare, parse_period

logger = logging.getLogger(__name__)  # "reports.api"


class CanUseReportsAPI(BasePermission):
    """users.use_reports_api: the groups Services and Analysts."""

    message = _("This account has no access to the reports API.")

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.has_perm("users.use_reports_api"))


# --- Parameters ----------------------------------------------------------------


class PeriodQuerySerializer(serializers.Serializer):
    """?period= or ?from=&to=: checked by the same code as the web pages."""

    period = serializers.ChoiceField(
        choices=PRESETS,
        required=False,
        help_text=f"The last N days, today included. Default: {DEFAULT_PRESET}.",
    )
    # "from" is a Python keyword: the field is named from_ and gets its name below
    from_ = serializers.DateField(
        required=False, help_text="First day (YYYY-MM-DD), together with 'to'."
    )
    to = serializers.DateField(required=False, help_text="Last day (YYYY-MM-DD), included.")

    def get_fields(self):
        fields = super().get_fields()
        fields["from"] = fields.pop("from_")
        return fields

    def validate(self, attrs):
        query = {key: str(value) for key, value in attrs.items()}
        try:
            attrs["period"] = parse_period(query)
        except PeriodError as error:
            raise serializers.ValidationError(str(error)) from error
        return attrs


class TopBooksQuerySerializer(PeriodQuerySerializer):
    limit = serializers.IntegerField(
        required=False, default=10, min_value=1, max_value=50, help_text="How many books (1-50)."
    )


# --- Answers ---------------------------------------------------------------------


class PeriodSerializer(serializers.Serializer):
    # "from" is a keyword again: source names the attribute, the field name is from
    def get_fields(self):
        return {
            "from": serializers.DateField(source="first"),
            "to": serializers.DateField(source="last"),
            "days": serializers.IntegerField(),
        }


def money():
    return serializers.DecimalField(max_digits=14, decimal_places=2)


def percent(help_text):
    return serializers.DecimalField(max_digits=5, decimal_places=1, help_text=help_text)


class TotalsSerializer(serializers.Serializer):
    orders = serializers.IntegerField(help_text="All orders, cancelled ones included.")
    paid_orders = serializers.IntegerField()
    cancelled_orders = serializers.IntegerField()
    revenue_uah = money()
    paid_revenue_uah = money()
    items_sold = serializers.IntegerField(help_text="Copies in orders that are not cancelled.")
    average_order_uah = money()
    paid_share = percent("Paid orders, % of all orders.")
    cancelled_share = percent("Cancelled orders, % of all orders.")
    new_customers = serializers.IntegerField()
    returning_customers = serializers.IntegerField()


class SummarySerializer(serializers.Serializer):
    period = PeriodSerializer()
    previous_period = PeriodSerializer(help_text="The same number of days right before.")
    totals = TotalsSerializer()
    previous_totals = TotalsSerializer()
    changes = serializers.DictField(
        child=serializers.DecimalField(max_digits=12, decimal_places=1, allow_null=True),
        help_text="Change against the previous period, %; null when it was 0.",
    )


class DaySerializer(TotalsSerializer):
    day = serializers.DateField()


class DailySerializer(serializers.Serializer):
    period = PeriodSerializer()
    days = DaySerializer(many=True, help_text="Every day of the period, zeros included.")


class BookSerializer(serializers.Serializer):
    source_id = serializers.IntegerField(help_text="The id of the book in the bookstore.")
    title = serializers.CharField()
    author = serializers.CharField()
    quantity = serializers.IntegerField(help_text="Copies sold.")
    revenue_uah = money()


class TopBooksSerializer(serializers.Serializer):
    period = PeriodSerializer()
    books = BookSerializer(many=True)


class FormatSerializer(serializers.Serializer):
    format_type = serializers.ChoiceField(choices=["paper", "ebook", "audio"])
    quantity = serializers.IntegerField()
    revenue_uah = money()
    revenue_share = percent("% of the revenue of all formats.")


class FormatsSerializer(serializers.Serializer):
    period = PeriodSerializer()
    formats = FormatSerializer(many=True)


# --- Views -----------------------------------------------------------------------

ERRORS = {
    400: OpenApiResponse(
        description="A bad period: unknown preset, a wrong date, from > to or more than 366 days.",
        examples=[
            OpenApiExample(
                "Reversed period",
                value={"non_field_errors": ["The start of the period is later than its end."]},
            )
        ],
    ),
    401: OpenApiResponse(description="No token, or the token has expired."),
    403: OpenApiResponse(description="The account has no permission users.use_reports_api."),
    429: OpenApiResponse(description="Too many requests: wait for Retry-After seconds."),
}


class ReportAPIView(APIView):
    """GET of one report: check the query, take the answer from the cache or
    compute it, log the call. A report overrides only get_data()."""

    permission_classes = [CanUseReportsAPI]
    # A limit per account ("reports" in DEFAULT_THROTTLE_RATES): a bug in a
    # client calling in a loop can't load the database
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "reports"
    query_serializer_class = PeriodQuerySerializer
    answer_serializer_class = None
    name = ""

    def get_data(self, period, params):
        raise NotImplementedError

    def get(self, request):
        query = self.query_serializer_class(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = dict(query.validated_data)
        period = params.pop("period")
        params.pop("from", None)
        params.pop("to", None)

        def compute():
            data = {"period": period, **self.get_data(period, params)}
            # .data: plain dicts and strings, safe to keep in the cache
            return self.answer_serializer_class(data).data

        # The real dates in the key, like the web pages ("period=30" moves daily)
        answer = cached_answer(
            f"api:{self.name}", {"first": period.first, "last": period.last, **params}, compute
        )
        logger.info(
            "API %s by %s: %s .. %s", self.name, request.user.username, period.first, period.last
        )
        return Response(answer)


def report_schema(answer, description, query=PeriodQuerySerializer, example=None):
    return extend_schema(
        tags=["reports"],
        description=description,
        parameters=[query],
        responses={200: answer, **ERRORS},
        examples=[OpenApiExample("Example", value=example, response_only=True)] if example else [],
    )


PERIOD_EXAMPLE = {"from": "2026-11-13", "to": "2026-11-19", "days": 7}


@report_schema(
    SummarySerializer,
    "Totals of the period and of the previous period of the same length (the KPI tiles).",
    example={
        "period": PERIOD_EXAMPLE,
        "previous_period": {"from": "2026-11-06", "to": "2026-11-12", "days": 7},
        "totals": {"orders": 12, "revenue_uah": "8400.00", "cancelled_share": "8.3"},
        "previous_totals": {"orders": 10, "revenue_uah": "7000.00", "cancelled_share": "10.0"},
        "changes": {"orders": "20.0", "revenue_uah": "20.0", "cancelled_share": "-17.0"},
    },
)
class SummaryAPIView(ReportAPIView):
    name = "summary"
    answer_serializer_class = SummarySerializer

    def get_data(self, period, params):
        totals = queries.summary(period)
        previous = queries.summary(period.previous)
        return {
            "previous_period": period.previous,
            "totals": totals,
            "previous_totals": previous,
            "changes": {key: compare(totals[key], previous[key])["percent"] for key in totals},
        }


@report_schema(
    DailySerializer,
    "Every day of the period: orders, revenue, customers (the revenue chart).",
    example={
        "period": PERIOD_EXAMPLE,
        "days": [{"day": "2026-11-19", "orders": 3, "revenue_uah": "2100.00"}],
    },
)
class DailyAPIView(ReportAPIView):
    name = "daily"
    answer_serializer_class = DailySerializer

    def get_data(self, period, params):
        return {"days": queries.sales_by(period, "day")}


@report_schema(
    TopBooksSerializer,
    "The best-selling books of the period by revenue; cancelled orders are not counted.",
    query=TopBooksQuerySerializer,
    example={
        "period": PERIOD_EXAMPLE,
        "books": [
            {
                "source_id": 42,
                "title": "Kobzar",
                "author": "Taras Shevchenko",
                "quantity": 5,
                "revenue_uah": "1750.00",
            }
        ],
    },
)
class TopBooksAPIView(ReportAPIView):
    name = "top-books"
    query_serializer_class = TopBooksQuerySerializer
    answer_serializer_class = TopBooksSerializer

    def get_data(self, period, params):
        return {"books": queries.top_books(period, limit=params["limit"])}


@report_schema(
    FormatsSerializer,
    "Copies and revenue of paper books, e-books and audiobooks.",
    example={
        "period": PERIOD_EXAMPLE,
        "formats": [
            {
                "format_type": "paper",
                "quantity": 8,
                "revenue_uah": "5600.00",
                "revenue_share": "80.0",
            }
        ],
    },
)
class FormatsAPIView(ReportAPIView):
    name = "formats"
    answer_serializer_class = FormatsSerializer

    def get_data(self, period, params):
        return {"formats": queries.formats(period)}

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenRefreshView

from config.views import health, sentry_debug
from reports import api as report_api
from users.api import ThrottledTokenObtainPairView

# REST API under /api/ (namespace "api"): tokens, the reports, the documentation
api_urlpatterns = [
    # JWT: username + password -> access + refresh; refresh -> a new access
    path("token/", ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # The reports for the bookstore's analytics page (reports/api.py)
    path("reports/summary/", report_api.SummaryAPIView.as_view(), name="reports_summary"),
    path("reports/daily/", report_api.DailyAPIView.as_view(), name="reports_daily"),
    path("reports/top-books/", report_api.TopBooksAPIView.as_view(), name="reports_top_books"),
    path("reports/formats/", report_api.FormatsAPIView.as_view(), name="reports_formats"),
    # OpenAPI schema (YAML) and Swagger UI built from it
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api:schema"), name="docs"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    # 200 / 503: are PostgreSQL and Redis reachable (docker-compose healthcheck)
    path("health/", health, name="health"),
    # Superuser only: raises an error to check Sentry (404 for anyone else)
    path("sentry-debug/", sentry_debug, name="sentry_debug"),
    # Django's language switcher: POST language=uk|en, next=<page> -> cookie.
    # Only the codes of settings.LANGUAGES are ever activated (LocaleMiddleware).
    path("i18n/", include("django.conf.urls.i18n")),
    # Login / logout: /accounts/login/, /accounts/logout/ (namespace "users")
    path("accounts/", include("users.urls")),
    path("api/", include((api_urlpatterns, "api"))),
    # The dashboard at the site root (namespace "reports")
    path("", include("reports.urls")),
]

if settings.ENABLE_DEBUG_TOOLBAR:
    # Imported here: without requirements-dev.txt the package doesn't exist
    from debug_toolbar.toolbar import debug_toolbar_urls

    urlpatterns += debug_toolbar_urls()

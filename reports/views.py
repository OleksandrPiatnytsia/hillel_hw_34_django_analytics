from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.views.generic import TemplateView


class AnalyticsAccessMixin(LoginRequiredMixin, PermissionRequiredMixin):
    """The access rule of every analytics page: logged in + users.view_analytics.

    An anonymous visitor goes to the login page (LoginRequiredMixin); a
    logged-in user without the permission gets 403 (raise_exception), not
    a login page again, which would look like a loop. The dashboard and the
    report pages (stage 4: ReportBaseView) inherit it instead of repeating it.
    """

    permission_required = "users.view_analytics"

    def handle_no_permission(self):
        # raise_exception only for logged-in users: anonymous ones still
        # get the redirect to the login page
        self.raise_exception = self.request.user.is_authenticated
        return super().handle_no_permission()


class DashboardView(AnalyticsAccessMixin, TemplateView):
    """The home page: KPI tiles and charts at stage 4, a placeholder for now."""

    template_name = "reports/dashboard.html"

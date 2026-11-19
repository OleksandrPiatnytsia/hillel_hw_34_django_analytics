from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("reports/sales/", views.SalesReportView.as_view(), name="sales"),
    path("reports/books/", views.BooksReportView.as_view(), name="books"),
    path("reports/books/<int:pk>/", views.BookReportView.as_view(), name="book"),
    path("reports/formats/", views.FormatsReportView.as_view(), name="formats"),
    path("reports/categories/", views.CategoriesReportView.as_view(), name="categories"),
    path("reports/customers/", views.CustomersReportView.as_view(), name="customers"),
    path("reports/cancellations/", views.CancellationsReportView.as_view(), name="cancellations"),
    path("reports/<slug:report>/export/", views.ExportCreateView.as_view(), name="export_create"),
    path("exports/", views.ExportListView.as_view(), name="exports"),
    path("exports/<int:pk>/download/", views.ExportDownloadView.as_view(), name="export_download"),
    path("orders/", views.OrderListView.as_view(), name="orders"),
    path("events/", views.EventListView.as_view(), name="events"),
]

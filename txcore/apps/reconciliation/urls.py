from django.urls import path
from .views import ReconciliationUploadView, ReconciliationRunDetailView, ReconciliationRunListView

urlpatterns = [
    path("", ReconciliationRunListView.as_view(), name="reconciliation-list"),
    path("upload/", ReconciliationUploadView.as_view(), name="reconciliation-upload"),
    path("<uuid:run_id>/", ReconciliationRunDetailView.as_view(), name="reconciliation-detail"),
]

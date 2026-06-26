from django.urls import path
from .views import WebhookIngestView, WebhookEventListView

urlpatterns = [
    path("", WebhookEventListView.as_view(), name="webhook-list"),
    path("ingest/<str:provider>/", WebhookIngestView.as_view(), name="webhook-ingest"),
]

from django.urls import path
from .views import TransactionCreateView, TransactionDetailView, TransactionListView

urlpatterns = [
    path("", TransactionListView.as_view(), name="transaction-list"),
    path("create/", TransactionCreateView.as_view(), name="transaction-create"),
    path("<str:reference>/", TransactionDetailView.as_view(), name="transaction-detail"),
]

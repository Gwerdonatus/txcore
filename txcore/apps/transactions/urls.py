from django.urls import path
from .checkout import CheckoutView
from .views import TransactionCreateView, TransactionDetailView, TransactionListView

urlpatterns = [
    path("", TransactionListView.as_view(), name="transaction-list"),
    path("create/", TransactionCreateView.as_view(), name="transaction-create"),
    path("<str:reference>/checkout/", CheckoutView.as_view(), name="transaction-checkout"),
    path("<str:reference>/", TransactionDetailView.as_view(), name="transaction-detail"),
]

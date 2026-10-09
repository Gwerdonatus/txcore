"""PostgreSQL-only checks for actual unique constraints and row locks."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import connection, connections, close_old_connections
from rest_framework.test import APIClient
from txcore.apps.transactions.models import Transaction, OutboxEvent


@pytest.mark.django_db(transaction=True)
def test_concurrent_intake_creates_one_transaction_and_one_event():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL uniqueness and transaction behavior.")
    user = get_user_model().objects.create_user(username="concurrent", is_staff=True)
    barrier = Barrier(4)

    def post():
        close_old_connections()
        try:
            client = APIClient()
            client.force_authenticate(user=user)
            barrier.wait(timeout=10)
            response = client.post(
                "/api/v1/transactions/create/",
                {
                    "amount": "25.00",
                    "currency": "USD",
                    "provider": "stripe",
                },
                format="json",
                HTTP_IDEMPOTENCY_KEY="concurrent-order",
            )
            return response.status_code, response.data["id"]
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: post(), range(4)))
    assert sorted(status for status, _ in results) == [200, 200, 200, 201]
    assert len({str(identifier) for _, identifier in results}) == 1
    assert Transaction.objects.count() == OutboxEvent.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_checkout_initializes_provider_once():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locking.")
    user = get_user_model().objects.create_user(username="checkout-concurrent", is_staff=True)
    payment = Transaction.objects.create(
        reference="TXN-CONCURRENT",
        idempotency_key="checkout",
        amount="25.00",
        currency="USD",
        provider="stripe",
    )
    session = SimpleNamespace(
        id="cs_test_concurrent", livemode=False, url="https://checkout.stripe.com/c/pay/concurrent"
    )
    barrier = Barrier(4)

    def post():
        close_old_connections()
        try:
            client = APIClient()
            client.force_authenticate(user=user)
            barrier.wait(timeout=10)
            return client.post(f"/api/v1/transactions/{payment.reference}/checkout/").status_code
        finally:
            connections.close_all()

    with patch("txcore.apps.transactions.checkout.create_checkout", return_value=session) as provider:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: post(), range(4)))
    assert results == [200] * 4
    provider.assert_called_once()

import uuid
import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from unittest.mock import patch

from txcore.apps.transactions.models import Transaction
from txcore.core.idempotency import delete_cached_response


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def idempotency_key():
    return f"test-key-{uuid.uuid4().hex}"


@pytest.fixture
def valid_payload():
    return {
        "amount": "150.00",
        "currency": "USD",
        "description": "Test payment",
        "provider": "stripe",
    }


@pytest.mark.django_db
class TestTransactionCreate:
    def test_creates_transaction_successfully(self, client, idempotency_key, valid_payload):
        with patch("txcore.apps.transactions.views.publish", return_value=True):
            response = client.post(
                "/api/v1/transactions/create/",
                data=valid_payload,
                format="json",
                HTTP_IDEMPOTENCY_KEY=idempotency_key,
            )

        assert response.status_code == 201
        data = response.json()
        assert data["amount"] == "150.0000"
        assert data["currency"] == "USD"
        assert data["status"] == "pending"
        assert data["reference"].startswith("TXN-")

    def test_idempotency_returns_same_response(self, client, idempotency_key, valid_payload):
        with patch("txcore.apps.transactions.views.publish", return_value=True):
            r1 = client.post(
                "/api/v1/transactions/create/",
                data=valid_payload,
                format="json",
                HTTP_IDEMPOTENCY_KEY=idempotency_key,
            )
            r2 = client.post(
                "/api/v1/transactions/create/",
                data=valid_payload,
                format="json",
                HTTP_IDEMPOTENCY_KEY=idempotency_key,
            )

        assert r1.status_code == 201
        assert r2.status_code == 200
        assert r1.json()["reference"] == r2.json()["reference"]
        # Only one DB record should exist
        assert Transaction.objects.filter(idempotency_key=idempotency_key).count() == 1

    def test_missing_idempotency_key_returns_400(self, client, valid_payload):
        response = client.post(
            "/api/v1/transactions/create/",
            data=valid_payload,
            format="json",
        )
        assert response.status_code == 400
        assert "Idempotency-Key" in str(response.json())

    def test_negative_amount_returns_422(self, client, idempotency_key):
        payload = {"amount": "-50.00", "currency": "USD"}
        response = client.post(
            "/api/v1/transactions/create/",
            data=payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=idempotency_key,
        )
        assert response.status_code == 422

    def test_zero_amount_returns_422(self, client, idempotency_key):
        payload = {"amount": "0.00", "currency": "USD"}
        response = client.post(
            "/api/v1/transactions/create/",
            data=payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=idempotency_key,
        )
        assert response.status_code == 422

    def test_missing_amount_returns_422(self, client, idempotency_key):
        response = client.post(
            "/api/v1/transactions/create/",
            data={"currency": "USD"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=idempotency_key,
        )
        assert response.status_code == 422


@pytest.mark.django_db
class TestTransactionDetail:
    def test_returns_transaction_by_reference(self, client):
        tx = Transaction.objects.create(
            idempotency_key=uuid.uuid4().hex,
            reference="TXN-TESTREF001",
            amount="200.00",
            currency="EUR",
            status=Transaction.Status.SETTLED,
        )
        response = client.get(f"/api/v1/transactions/{tx.reference}/")
        assert response.status_code == 200
        assert response.json()["reference"] == "TXN-TESTREF001"

    def test_returns_404_for_unknown_reference(self, client):
        response = client.get("/api/v1/transactions/TXN-DOESNOTEXIST/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestTransactionList:
    def test_returns_all_transactions(self, client):
        Transaction.objects.create(
            idempotency_key=uuid.uuid4().hex,
            reference="TXN-LIST001",
            amount="100.00",
            currency="USD",
            status=Transaction.Status.PENDING,
        )
        response = client.get("/api/v1/transactions/")
        assert response.status_code == 200
        assert response.json()["count"] >= 1

    def test_filters_by_status(self, client):
        Transaction.objects.create(
            idempotency_key=uuid.uuid4().hex,
            reference="TXN-SETTLED001",
            amount="100.00",
            currency="USD",
            status=Transaction.Status.SETTLED,
        )
        Transaction.objects.create(
            idempotency_key=uuid.uuid4().hex,
            reference="TXN-PENDING001",
            amount="200.00",
            currency="USD",
            status=Transaction.Status.PENDING,
        )
        response = client.get("/api/v1/transactions/?status=settled")
        assert response.status_code == 200
        results = response.json()["results"]
        assert all(r["status"] == "settled" for r in results)

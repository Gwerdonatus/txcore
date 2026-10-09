import uuid
import pytest
from rest_framework.test import APIClient
from django.core.files.uploadedfile import SimpleUploadedFile

from txcore.apps.transactions.models import Transaction
from txcore.apps.reconciliation.models import ReconciliationRun, ReconciliationDiscrepancy
from txcore.apps.reconciliation.engine import run_reconciliation


@pytest.fixture
def client(db):
    from django.contrib.auth import get_user_model
    user = get_user_model().objects.create_user(username="operator", password="test-password", is_staff=True)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def make_transaction(reference, amount="100.00", currency="USD", status="settled"):
    return Transaction.objects.create(
        idempotency_key=uuid.uuid4().hex,
        reference=reference,
        amount=amount,
        currency=currency,
        status=status,
    )


def make_csv(rows: list[dict]) -> str:
    lines = ["reference,amount,currency,status"]
    for r in rows:
        lines.append(
            f"{r['reference']},{r['amount']},"
            f"{r.get('currency', 'USD')},{r.get('status', 'settled')}"
        )
    return "\n".join(lines)


@pytest.mark.django_db
class TestReconciliationEngine:
    def test_all_matched(self):
        make_transaction("TXN-RECON001", amount="100.00")
        make_transaction("TXN-RECON002", amount="200.00")

        csv = make_csv([
            {"reference": "TXN-RECON001", "amount": "100.00"},
            {"reference": "TXN-RECON002", "amount": "200.00"},
        ])

        run = ReconciliationRun.objects.create(filename="test.csv")
        result = run_reconciliation(run, csv)

        assert result.status == ReconciliationRun.Status.COMPLETED
        assert result.matched == 2
        assert result.discrepancies == 0

    def test_detects_amount_mismatch(self):
        make_transaction("TXN-MISMATCH001", amount="100.00")

        csv = make_csv([{"reference": "TXN-MISMATCH001", "amount": "99.00"}])
        run = ReconciliationRun.objects.create(filename="test.csv")
        result = run_reconciliation(run, csv)

        assert result.discrepancies == 1
        d = ReconciliationDiscrepancy.objects.get(run=result)
        assert d.discrepancy_type == ReconciliationDiscrepancy.Type.AMOUNT_MISMATCH

    def test_detects_not_found(self):
        csv = make_csv([{"reference": "TXN-GHOST001", "amount": "500.00"}])
        run = ReconciliationRun.objects.create(filename="test.csv")
        result = run_reconciliation(run, csv)

        assert result.discrepancies == 1
        d = ReconciliationDiscrepancy.objects.get(run=result)
        assert d.discrepancy_type == ReconciliationDiscrepancy.Type.NOT_FOUND

    def test_detects_status_mismatch(self):
        make_transaction("TXN-STATUS001", status="pending")

        csv = make_csv([{"reference": "TXN-STATUS001", "amount": "100.00", "status": "settled"}])
        run = ReconciliationRun.objects.create(filename="test.csv")
        result = run_reconciliation(run, csv)

        assert result.discrepancies == 1
        d = ReconciliationDiscrepancy.objects.get(run=result)
        assert d.discrepancy_type == ReconciliationDiscrepancy.Type.STATUS_MISMATCH

    def test_mixed_results(self):
        make_transaction("TXN-MIX001", amount="100.00")
        make_transaction("TXN-MIX002", amount="200.00")

        csv = make_csv([
            {"reference": "TXN-MIX001", "amount": "100.00"},   # match
            {"reference": "TXN-MIX002", "amount": "999.00"},   # mismatch
            {"reference": "TXN-MIX003", "amount": "50.00"},    # not found
        ])
        run = ReconciliationRun.objects.create(filename="test.csv")
        result = run_reconciliation(run, csv)

        assert result.matched == 1
        assert result.discrepancies == 2
        assert result.total_rows == 3

    def test_missing_required_columns_fails(self):
        csv = "ref,amt\nTXN-001,100.00"
        run = ReconciliationRun.objects.create(filename="bad.csv")
        result = run_reconciliation(run, csv)

        assert result.status == ReconciliationRun.Status.FAILED
        assert "missing required columns" in result.error_message.lower()

    def test_skips_invalid_amount_rows(self):
        make_transaction("TXN-SKIP001")
        csv = "reference,amount,currency,status\nTXN-SKIP001,not-a-number,USD,settled"
        run = ReconciliationRun.objects.create(filename="test.csv")
        result = run_reconciliation(run, csv)

        assert result.skipped == 1
        assert result.matched == 0


@pytest.mark.django_db
class TestReconciliationAPI:
    def test_upload_csv_via_api(self, client):
        make_transaction("TXN-API001", amount="150.00")

        csv_content = make_csv([{"reference": "TXN-API001", "amount": "150.00"}])
        csv_file = SimpleUploadedFile("recon.csv", csv_content.encode(), content_type="text/csv")

        response = client.post(
            "/api/v1/reconciliation/upload/",
            {"file": csv_file},
            format="multipart",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "completed"
        assert data["matched"] == 1

    def test_upload_non_csv_rejected(self, client):
        txt_file = SimpleUploadedFile("data.txt", b"hello", content_type="text/plain")
        response = client.post(
            "/api/v1/reconciliation/upload/",
            {"file": txt_file},
            format="multipart",
        )
        assert response.status_code == 400

    def test_upload_without_file_rejected(self, client):
        response = client.post("/api/v1/reconciliation/upload/", {}, format="multipart")
        assert response.status_code == 400

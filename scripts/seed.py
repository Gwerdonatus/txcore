#!/usr/bin/env python
"""
Seed script: populates the database with realistic sample data.
Run with: python scripts/seed.py

Useful for demos, screenshots, and load test prep.
"""
import os
import sys
import uuid
import random
from decimal import Decimal

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "txcore.settings")

import django
django.setup()

from txcore.apps.transactions.models import Transaction
from txcore.apps.webhooks.models import WebhookEvent
from txcore.apps.reconciliation.models import ReconciliationRun, ReconciliationDiscrepancy

CURRENCIES = ["USD", "EUR", "GBP", "NGN", "JPY"]
PROVIDERS = ["stripe", "paystack", "paypal", "flutterwave"]
STATUSES = ["pending", "settled", "failed", "processing"]
WEBHOOK_EVENTS = ["payment.success", "payment.failed", "refund.created", "dispute.opened"]


def seed_transactions(count=50):
    print(f"Seeding {count} transactions...")
    created = 0
    for _ in range(count):
        try:
            Transaction.objects.create(
                idempotency_key=uuid.uuid4().hex,
                reference=f"TXN-{uuid.uuid4().hex[:10].upper()}",
                amount=Decimal(str(round(random.uniform(10, 50000), 2))),
                currency=random.choice(CURRENCIES),
                status=random.choice(STATUSES),
                description="Seeded transaction",
                provider=random.choice(PROVIDERS),
            )
            created += 1
        except Exception as e:
            print(f"  Skipped: {e}")
    print(f"  Created {created} transactions.")


def seed_webhooks(count=20):
    print(f"Seeding {count} webhook events...")
    for _ in range(count):
        WebhookEvent.objects.create(
            provider=random.choice(PROVIDERS),
            event_type=random.choice(WEBHOOK_EVENTS),
            payload={"event": "seeded", "reference": f"TXN-{uuid.uuid4().hex[:8].upper()}"},
            signature="seeded",
            status=random.choice(["received", "processed", "failed"]),
        )
    print(f"  Created {count} webhook events.")


def seed_reconciliation():
    print("Seeding reconciliation run with discrepancies...")
    run = ReconciliationRun.objects.create(
        filename="sample_bank_statement.csv",
        status="completed",
        total_rows=10,
        matched=7,
        discrepancies=3,
        skipped=0,
    )
    for dtype in ["amount_mismatch", "not_found", "status_mismatch"]:
        ReconciliationDiscrepancy.objects.create(
            run=run,
            reference=f"TXN-{uuid.uuid4().hex[:8].upper()}",
            discrepancy_type=dtype,
            expected_amount=Decimal("100.00"),
            actual_amount=Decimal("99.50") if dtype == "amount_mismatch" else None,
            notes=f"Seeded {dtype} discrepancy",
        )
    print(f"  Created reconciliation run {run.id} with 3 discrepancies.")


if __name__ == "__main__":
    print("=== TxCore Seed Script ===")
    seed_transactions(50)
    seed_webhooks(20)
    seed_reconciliation()
    print("\nDone. Database is ready for demo.")

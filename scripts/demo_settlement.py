"""Dispatch a synthetic settlement through the real Celery worker; no provider call."""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "txcore.settings")

import django

django.setup()

from txcore.apps.transactions.models import Transaction
from txcore.workers.settlement import process_settlement

transaction, _ = Transaction.objects.get_or_create(
    idempotency_key="txcore-recruiter-settlement-v1",
    defaults={"reference": "TXN-DEMO-SETTLEMENT", "amount": "42.00", "currency": "EUR",
              "provider": "demo", "description": "Synthetic worker demo; no funds moved",
              "metadata": {"demo_data": True, "external_actions_performed": False}},
)
if transaction.status == Transaction.Status.PENDING:
    process_settlement.delay(str(transaction.id))
for _ in range(60):
    transaction.refresh_from_db()
    if transaction.status == Transaction.Status.SETTLED:
        print(f"{transaction.reference}: settled by Celery (simulated; no funds moved)")
        break
    time.sleep(1)
else:
    raise RuntimeError(f"Worker did not settle the demo transaction: {transaction.status}")

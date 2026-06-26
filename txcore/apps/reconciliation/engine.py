import csv
import io
import logging
from decimal import Decimal, InvalidOperation
from django.utils import timezone

from txcore.core.metrics import RECONCILIATION_RUNS, RECONCILIATION_DISCREPANCIES
from txcore.apps.transactions.models import Transaction
from .models import ReconciliationRun, ReconciliationDiscrepancy

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"reference", "amount", "currency"}


def run_reconciliation(run: ReconciliationRun, csv_content: str) -> ReconciliationRun:
    """
    Core reconciliation engine.
    Reads CSV rows, matches to DB transactions, flags discrepancies.

    CSV format:
        reference,amount,currency,status
        TXN-ABC123,100.00,USD,settled
    """
    run.status = ReconciliationRun.Status.RUNNING
    run.save(update_fields=["status"])

    matched = 0
    discrepancies = 0
    skipped = 0

    try:
        reader = csv.DictReader(io.StringIO(csv_content))

        # Validate headers
        if not REQUIRED_COLUMNS.issubset(set(reader.fieldnames or [])):
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            raise ValueError(f"CSV missing required columns: {missing}")

        rows = list(reader)
        run.total_rows = len(rows)
        run.save(update_fields=["total_rows"])

        # Bulk fetch matching transactions to avoid N+1
        references = [row.get("reference", "").strip() for row in rows]
        tx_map = {
            tx.reference: tx
            for tx in Transaction.objects.filter(reference__in=references)
        }

        discrepancy_objects = []

        for row in rows:
            reference = row.get("reference", "").strip()
            if not reference:
                skipped += 1
                continue

            try:
                csv_amount = Decimal(row.get("amount", "0").strip())
            except InvalidOperation:
                skipped += 1
                logger.warning("Invalid amount in CSV row: %s", row)
                continue

            csv_status = row.get("status", "").strip().lower()
            transaction = tx_map.get(reference)

            if transaction is None:
                discrepancy_objects.append(
                    ReconciliationDiscrepancy(
                        run=run,
                        reference=reference,
                        discrepancy_type=ReconciliationDiscrepancy.Type.NOT_FOUND,
                        expected_amount=csv_amount,
                        notes=f"Transaction {reference} not found in database",
                    )
                )
                discrepancies += 1
                continue

            # Check amount match (within 0.01 tolerance for floating point)
            if abs(transaction.amount - csv_amount) > Decimal("0.01"):
                discrepancy_objects.append(
                    ReconciliationDiscrepancy(
                        run=run,
                        reference=reference,
                        discrepancy_type=ReconciliationDiscrepancy.Type.AMOUNT_MISMATCH,
                        expected_amount=csv_amount,
                        actual_amount=transaction.amount,
                        notes=f"CSV amount {csv_amount} != DB amount {transaction.amount}",
                    )
                )
                discrepancies += 1
                continue

            # Check status match if provided
            if csv_status and csv_status != transaction.status:
                discrepancy_objects.append(
                    ReconciliationDiscrepancy(
                        run=run,
                        reference=reference,
                        discrepancy_type=ReconciliationDiscrepancy.Type.STATUS_MISMATCH,
                        expected_status=csv_status,
                        actual_status=transaction.status,
                        actual_amount=transaction.amount,
                        notes=f"CSV status {csv_status} != DB status {transaction.status}",
                    )
                )
                discrepancies += 1
                continue

            matched += 1

        # Bulk insert discrepancies
        if discrepancy_objects:
            ReconciliationDiscrepancy.objects.bulk_create(discrepancy_objects)

        run.matched = matched
        run.discrepancies = discrepancies
        run.skipped = skipped
        run.status = ReconciliationRun.Status.COMPLETED
        run.completed_at = timezone.now()
        run.save(update_fields=["matched", "discrepancies", "skipped", "status", "completed_at"])

        RECONCILIATION_RUNS.labels(status="completed").inc()
        RECONCILIATION_DISCREPANCIES.set(discrepancies)

        logger.info(
            "Reconciliation complete: matched=%d discrepancies=%d skipped=%d",
            matched, discrepancies, skipped,
        )

    except Exception as exc:
        run.status = ReconciliationRun.Status.FAILED
        run.error_message = str(exc)
        run.save(update_fields=["status", "error_message"])
        RECONCILIATION_RUNS.labels(status="failed").inc()
        logger.exception("Reconciliation run %s failed: %s", run.id, exc)

    return run

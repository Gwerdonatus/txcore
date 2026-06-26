import logging
import time
from celery import shared_task
from django.utils import timezone

from txcore.core.metrics import CELERY_TASKS_PROCESSED, CELERY_TASK_DURATION
from txcore.apps.transactions.models import Transaction
from txcore.events.kafka_producer import publish

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=5,
    default_retry_delay=60,
    name="workers.process_settlement",
)
def process_settlement(self, transaction_id: str):
    """
    Async settlement worker.
    Moves a PENDING transaction through to SETTLED with exponential backoff retries.
    """
    start = time.monotonic()
    task_name = "process_settlement"

    try:
        transaction = Transaction.objects.get(id=transaction_id)
    except Transaction.DoesNotExist:
        logger.error("Settlement worker: transaction %s not found", transaction_id)
        CELERY_TASKS_PROCESSED.labels(task_name=task_name, status="not_found").inc()
        return

    if transaction.status != Transaction.Status.PENDING:
        logger.info("Settlement skipped — transaction %s is already %s", transaction_id, transaction.status)
        CELERY_TASKS_PROCESSED.labels(task_name=task_name, status="skipped").inc()
        return

    try:
        # Mark as processing
        transaction.status = Transaction.Status.PROCESSING
        transaction.save(update_fields=["status", "updated_at"])

        # Simulate provider settlement call (replace with real provider SDK)
        logger.info("Settling transaction %s with provider: %s", transaction.reference, transaction.provider or "default")

        # Mark as settled
        transaction.status = Transaction.Status.SETTLED
        transaction.settled_at = timezone.now()
        transaction.save(update_fields=["status", "settled_at", "updated_at"])

        publish(
            "transactions",
            key=str(transaction.id),
            payload={
                "event": "payment_settled",
                "transaction_id": str(transaction.id),
                "reference": transaction.reference,
                "amount": str(transaction.amount),
                "currency": transaction.currency,
            },
        )

        duration = time.monotonic() - start
        CELERY_TASK_DURATION.labels(task_name=task_name).observe(duration)
        CELERY_TASKS_PROCESSED.labels(task_name=task_name, status="success").inc()
        logger.info("Transaction settled: %s", transaction.reference)

    except Exception as exc:
        duration = time.monotonic() - start
        CELERY_TASK_DURATION.labels(task_name=task_name).observe(duration)
        CELERY_TASKS_PROCESSED.labels(task_name=task_name, status="error").inc()

        # Exponential backoff: 60s, 120s, 240s, 480s, 960s
        retry_delay = 60 * (2 ** self.request.retries)
        logger.warning(
            "Settlement failed for %s (attempt %d/%d): %s",
            transaction_id, self.request.retries + 1, self.max_retries, exc,
        )
        raise self.retry(exc=exc, countdown=retry_delay)

import logging
import time
from datetime import timedelta
from celery import shared_task
from django.utils import timezone

from txcore.core.metrics import CELERY_TASKS_PROCESSED, CELERY_TASK_DURATION
from txcore.apps.transactions.models import Transaction
from txcore.events.kafka_producer import publish

logger = logging.getLogger(__name__)

SLA_THRESHOLD_MINUTES = 30  # Transactions pending > 30 min trigger an alert


@shared_task(name="workers.check_sla_breaches")
def check_sla_breaches():
    """
    Periodic task: scan for transactions breaching SLA thresholds.
    Should be scheduled via Celery Beat every 5 minutes.
    """
    start = time.monotonic()
    task_name = "check_sla_breaches"

    threshold = timezone.now() - timedelta(minutes=SLA_THRESHOLD_MINUTES)

    breaching = Transaction.objects.filter(
        status__in=[Transaction.Status.PENDING, Transaction.Status.PROCESSING],
        created_at__lt=threshold,
    ).only("id", "reference", "amount", "currency", "status", "created_at")

    count = 0
    for transaction in breaching:
        age_minutes = int((timezone.now() - transaction.created_at).total_seconds() / 60)

        publish(
            "alerts",
            key=str(transaction.id),
            payload={
                "event": "sla_breach",
                "transaction_id": str(transaction.id),
                "reference": transaction.reference,
                "status": transaction.status,
                "age_minutes": age_minutes,
                "amount": str(transaction.amount),
                "currency": transaction.currency,
            },
        )

        logger.warning(
            "SLA breach: %s has been %s for %d minutes",
            transaction.reference, transaction.status, age_minutes,
        )
        count += 1

    duration = time.monotonic() - start
    CELERY_TASK_DURATION.labels(task_name=task_name).observe(duration)
    CELERY_TASKS_PROCESSED.labels(task_name=task_name, status="success").inc()

    if count:
        logger.warning("SLA check: %d transactions breaching threshold", count)
    else:
        logger.info("SLA check: all transactions within threshold")

    return {"breaching_count": count}

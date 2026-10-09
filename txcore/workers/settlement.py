"""Explicit local simulation only; never handles Stripe transactions."""

from celery import shared_task
from django.db import transaction as db_transaction
from django.utils import timezone
from txcore.apps.transactions.models import Transaction
from txcore.events.outbox import enqueue


@shared_task(bind=True, name="workers.process_settlement", max_retries=5)
def process_settlement(self, transaction_id):
    try:
        with db_transaction.atomic():
            tx = Transaction.objects.select_for_update().filter(id=transaction_id).first()
            if tx is None or tx.provider != "demo" or tx.status not in {"pending", "processing"}:
                return
            tx.status = Transaction.Status.SETTLED
            tx.settled_at = timezone.now()
            tx.save(update_fields=["status", "settled_at", "updated_at"])
            enqueue(
                "transactions",
                tx.id,
                "payment_settled",
                {
                    "transaction_id": str(tx.id),
                    "reference": tx.reference,
                    "amount": str(tx.amount),
                    "currency": tx.currency,
                    "simulation": True,
                },
            )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=min(960, 60 * 2**self.request.retries))

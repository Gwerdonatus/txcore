"""Durably stored webhooks are polled; broker loss cannot erase them."""

import logging
from datetime import timedelta
from celery import shared_task
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from txcore.apps.transactions.models import Transaction
from txcore.apps.webhooks.models import WebhookEvent
from txcore.events.outbox import enqueue
from txcore.providers.stripe import client, minor_units

logger = logging.getLogger(__name__)


class InvalidPayment(ValueError):
    pass


def apply_stripe_payment(event):
    obj = event.payload.get("data", {}).get("object", {})
    if not isinstance(obj, dict) or not isinstance(obj.get("id"), str):
        raise InvalidPayment("Missing Checkout session.")
    if event.event_type not in {
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
        "checkout.session.async_payment_failed",
        "checkout.session.expired",
    }:
        return
    event.transaction_reference = verify_checkout(obj["id"], event.event_type).reference


def verify_checkout(session_id, event_type=""):
    # Retrieve current provider state; browser redirects and stale/out-of-order
    # webhook payloads are never sufficient proof of payment.
    session = client().v1.checkout.sessions.retrieve(session_id)
    if session.livemode or not session.id.startswith("cs_test_"):
        raise InvalidPayment("Live sessions are disabled.")
    try:
        tx = Transaction.objects.select_for_update().get(provider="stripe", provider_reference=session.id)
    except Transaction.DoesNotExist:
        raise InvalidPayment("Checkout session does not belong to a TxCore transaction.")
    if session.client_reference_id != tx.reference:
        raise InvalidPayment("Checkout reference mismatch.")
    if session.amount_total != minor_units(tx.amount, tx.currency) or session.currency.upper() != tx.currency:
        raise InvalidPayment("Provider amount or currency differs from the transaction.")
    if tx.status in {Transaction.Status.SETTLED, Transaction.Status.REVERSED}:
        return tx
    if session.payment_status == "paid" and session.status == "complete":
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
                "provider": "stripe",
                "sandbox": True,
            },
        )
    elif session.status == "expired":
        tx.status = Transaction.Status.FAILED
        tx.save(update_fields=["status", "updated_at"])
    elif event_type == "checkout.session.async_payment_failed":
        raise InvalidPayment("Asynchronous payment failure requires provider review.")

    return tx


@shared_task(name="workers.process_webhooks")
def process_webhooks():
    ids = list(
        WebhookEvent.objects.filter(status=WebhookEvent.Status.RECEIVED)
        .filter(
            Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=timezone.now()),
        )
        .values_list("id", flat=True)[:100]
    )
    processed = 0
    for event_id in ids:
        try:
            with transaction.atomic():
                event = WebhookEvent.objects.select_for_update().get(id=event_id)
                if event.status != WebhookEvent.Status.RECEIVED:
                    continue
                if event.provider == "stripe":
                    apply_stripe_payment(event)
                # Demo events are reporting only and cannot settle Stripe payments.
                event.status = WebhookEvent.Status.PROCESSED
                event.processed_at = timezone.now()
                event.last_error = ""
                event.save()
                processed += 1
        except Exception as exc:
            with transaction.atomic():
                event = WebhookEvent.objects.select_for_update().get(id=event_id)
                if event.status != WebhookEvent.Status.RECEIVED:
                    continue
                event.retry_count += 1
                event.last_error = (
                    "Payment validation failed."
                    if isinstance(exc, InvalidPayment)
                    else "Provider unavailable."
                )
                if isinstance(exc, InvalidPayment) or event.retry_count >= 5:
                    event.status = WebhookEvent.Status.FAILED
                event.next_attempt_at = timezone.now() + timedelta(seconds=5 * 2**event.retry_count)
                event.save()
    return {"processed": processed}


@shared_task(name="workers.recover_provider_payments")
def recover_provider_payments():
    """Provider-state recovery for missed webhooks; never trusts a browser return."""
    ids = list(
        Transaction.objects.filter(provider="stripe", status="processing")
        .exclude(provider_reference="")
        .values_list("id", flat=True)[:20]
    )
    recovered = 0
    for tx_id in ids:
        try:
            with transaction.atomic():
                payment = (
                    Transaction.objects.select_for_update(skip_locked=True)
                    .filter(
                        id=tx_id,
                        status="processing",
                    )
                    .first()
                )
                if payment is None:
                    continue
                verified = verify_checkout(payment.provider_reference)
                if verified.status == "settled":
                    recovered += 1
        except Exception as exc:
            logger.warning("Provider recovery retained %s for retry (%s)", tx_id, type(exc).__name__)
            # Leave the payment recoverable for the next periodic scan.
            continue
    return {"recovered": recovered}

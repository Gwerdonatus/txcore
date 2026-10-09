"""Stripe-hosted sandbox Checkout. No card data enters TxCore."""

from decimal import Decimal
from django.conf import settings
import stripe


class SandboxNotConfigured(Exception):
    pass


def client():
    if not settings.STRIPE_SECRET_KEY.startswith("sk_test_"):
        raise SandboxNotConfigured("Configure a Stripe sandbox secret key (sk_test_). Live mode is disabled.")
    return stripe.StripeClient(
        settings.STRIPE_SECRET_KEY,
        max_network_retries=2,
        http_client=stripe.RequestsClient(timeout=10),
    )


def minor_units(amount, currency):
    scale = Decimal("1") if currency.upper() == "JPY" else Decimal("100")
    units = amount * scale
    if not units.is_finite() or units != units.to_integral_value() or units <= 0:
        raise ValueError("Amount must match the currency's minor-unit precision.")
    return int(units)


def create_checkout(tx):
    return client().v1.checkout.sessions.create(
        {
            "mode": "payment",
            "client_reference_id": tx.reference,
            "metadata": {"transaction_id": str(tx.id)},
            "line_items": [
                {
                    "price_data": {
                        "currency": tx.currency.lower(),
                        "unit_amount": minor_units(tx.amount, tx.currency),
                        "product_data": {"name": tx.description or tx.reference},
                    },
                    "quantity": 1,
                }
            ],
            "success_url": settings.CHECKOUT_RETURN_URL + "?session_id={CHECKOUT_SESSION_ID}",
            "cancel_url": settings.CHECKOUT_RETURN_URL + "?cancelled=1",
        },
        options={"idempotency_key": "checkout-v1-" + str(tx.id)},
    )


def verify_event(body, signature):
    if not settings.STRIPE_WEBHOOK_SECRET.startswith("whsec_"):
        raise SandboxNotConfigured("Configure the Stripe webhook signing secret.")
    return stripe.Webhook.construct_event(body, signature, settings.STRIPE_WEBHOOK_SECRET, tolerance=300)

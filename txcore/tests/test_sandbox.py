"""Security, provider contracts and durable retry regressions (no live API calls)."""

import hashlib
import hmac
import json
import time
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from txcore.apps.transactions.models import Transaction, OutboxEvent
from txcore.apps.webhooks.models import WebhookEvent
from txcore.apps.reconciliation.models import ReconciliationRun, ReconciliationDiscrepancy
from txcore.apps.reconciliation.engine import run_reconciliation
from txcore.providers.stripe import minor_units, client as stripe_client, SandboxNotConfigured
from txcore.workers.delivery import deliver_outbox
from txcore.workers.webhooks import process_webhooks
from txcore.workers.settlement import process_settlement


@pytest.fixture
def operator():
    return get_user_model().objects.create_user(
        username="sandbox-operator", password="password", is_staff=True
    )


@pytest.fixture
def api(operator):
    result = APIClient()
    result.force_authenticate(user=operator)
    return result


def tx(**kwargs):
    return Transaction.objects.create(
        reference="TXN-" + uuid.uuid4().hex[:12],
        idempotency_key=uuid.uuid4().hex,
        amount=kwargs.pop("amount", Decimal("25.00")),
        currency=kwargs.pop("currency", "USD"),
        provider=kwargs.pop("provider", "stripe"),
        **kwargs,
    )


def create(api, key="order-1", **changes):
    return api.post(
        "/api/v1/transactions/create/",
        {"amount": "25.00", "currency": "USD", "provider": "stripe", **changes},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )


def test_private_api_requires_authentication():
    assert APIClient().get("/api/v1/transactions/").status_code == 401


def test_non_staff_account_cannot_access_workspace():
    user = get_user_model().objects.create_user(username="ordinary")
    api = APIClient()
    api.force_authenticate(user=user)
    assert api.get("/api/v1/transactions/").status_code == 403


def test_login_works_and_session_write_requires_csrf(operator):
    api = APIClient(enforce_csrf_checks=True)
    assert api.login(username=operator.username, password="password")
    assert api.get("/").status_code == 200
    assert create(api).status_code == 403


def test_same_key_with_changed_body_is_conflict(api):
    assert create(api).status_code == 201
    assert create(api, amount="26.00").status_code == 409
    assert Transaction.objects.count() == OutboxEvent.objects.count() == 1


def test_idempotency_is_scoped_to_authenticated_caller(api):
    first = create(api)
    other = get_user_model().objects.create_user(username="other", is_staff=True)
    api.force_authenticate(user=other)
    second = create(api)
    assert first.status_code == second.status_code == 201
    assert first.data["id"] != second.data["id"]


def test_creation_and_event_intent_roll_back_together(api):
    with patch("txcore.apps.transactions.views.enqueue", side_effect=RuntimeError("database unavailable")):
        assert create(api).status_code == 500
    assert not Transaction.objects.exists()
    assert not OutboxEvent.objects.exists()


def test_oversized_idempotency_key_rejected(api):
    assert create(api, key="x" * 129).status_code == 400


def test_checkout_missing_config_fails_closed(api):
    payment = tx()
    with override_settings(STRIPE_SECRET_KEY=""):
        result = api.post(f"/api/v1/transactions/{payment.reference}/checkout/")
    assert result.status_code == 503
    payment.refresh_from_db()
    assert payment.status == "pending"


@pytest.mark.parametrize("key", ["", "sk_live_not_allowed", "rk_live_not_allowed"])
def test_live_and_missing_keys_never_initialize_provider(key):
    with override_settings(STRIPE_SECRET_KEY=key), pytest.raises(SandboxNotConfigured):
        stripe_client()


def test_checkout_reuses_session_and_keeps_payment_unsettled(api):
    payment = tx()
    session = SimpleNamespace(
        id="cs_test_checkout", livemode=False, url="https://checkout.stripe.com/c/pay/test"
    )
    with patch("txcore.apps.transactions.checkout.create_checkout", return_value=session) as provider:
        one = api.post(f"/api/v1/transactions/{payment.reference}/checkout/")
        two = api.post(f"/api/v1/transactions/{payment.reference}/checkout/")
    assert one.status_code == two.status_code == 200
    assert one.data == two.data
    provider.assert_called_once()
    payment.refresh_from_db()
    assert payment.status == "processing"
    assert payment.settled_at is None


def test_return_redirect_does_not_confirm_payment(api, operator):
    api.force_login(operator)
    payment = tx()
    assert api.get("/payments/return/?session_id=cs_test_fake").status_code == 200
    payment.refresh_from_db()
    assert payment.status == "pending"


def test_stripe_checkout_contract_has_stable_key_and_exact_amount():
    from txcore.providers.stripe import create_checkout

    payment = tx()
    with patch("txcore.providers.stripe.client") as provider:
        create_checkout(payment)
    call = provider.return_value.v1.checkout.sessions.create.call_args
    assert call.kwargs["options"]["idempotency_key"] == "checkout-v1-" + str(payment.id)
    assert call.args[0]["line_items"][0]["price_data"]["unit_amount"] == 2500
    assert call.args[0]["client_reference_id"] == payment.reference


@pytest.mark.parametrize("amount,currency,expected", [("12.34", "USD", 1234), ("100", "JPY", 100)])
def test_currency_minor_units(amount, currency, expected):
    assert minor_units(Decimal(amount), currency) == expected


@pytest.mark.parametrize("amount,currency", [("1.001", "USD"), ("1.5", "JPY"), ("0", "USD")])
def test_invalid_minor_unit_precision(amount, currency):
    with pytest.raises(ValueError):
        minor_units(Decimal(amount), currency)


def signed_stripe(payload, timestamp=None):
    body = json.dumps(payload).encode()
    timestamp = timestamp or int(time.time())
    digest = hmac.new(b"whsec_test", str(timestamp).encode() + b"." + body, hashlib.sha256).hexdigest()
    return body, f"t={timestamp},v1={digest}"


def stripe_event(event_id="evt_test_1"):
    return {
        "id": event_id,
        "object": "event",
        "livemode": False,
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_test_payment"}},
    }


def ingest(payload, timestamp=None):
    body, signature = signed_stripe(payload, timestamp)
    with override_settings(STRIPE_WEBHOOK_SECRET="whsec_test"):
        return APIClient().post(
            "/api/v1/webhooks/ingest/stripe/",
            body,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=signature,
        )


def test_stripe_signed_webhook_is_deduplicated():
    one, two = ingest(stripe_event()), ingest(stripe_event())
    assert one.status_code == two.status_code == 202
    assert one.data["event_id"] == two.data["event_id"]
    assert WebhookEvent.objects.count() == OutboxEvent.objects.count() == 1


def test_stale_stripe_signature_is_rejected():
    assert ingest(stripe_event(), int(time.time()) - 600).status_code == 400
    assert not WebhookEvent.objects.exists()


def test_live_stripe_event_is_rejected():
    assert ingest({**stripe_event(), "livemode": True}).status_code == 400


def test_changed_payload_for_same_provider_event_is_rejected():
    assert ingest(stripe_event()).status_code == 202
    assert ingest({**stripe_event(), "type": "checkout.session.expired"}).status_code == 409


def test_stripe_never_accepts_generic_demo_signature():
    with override_settings(STRIPE_WEBHOOK_SECRET="whsec_test"):
        response = APIClient().post(
            "/api/v1/webhooks/ingest/stripe/",
            b"{}",
            content_type="application/json",
            HTTP_X_WEBHOOK_SIGNATURE="anything",
        )
    assert response.status_code == 400


def stored_stripe_event():
    return WebhookEvent.objects.create(
        provider="stripe",
        provider_event_id="evt_worker",
        event_type="checkout.session.completed",
        payload=stripe_event(),
    )


def provider_session(payment, **overrides):
    return SimpleNamespace(
        id="cs_test_payment",
        livemode=False,
        client_reference_id=payment.reference,
        amount_total=2500,
        currency="usd",
        payment_status="paid",
        status="complete",
        **overrides,
    )


def test_provider_verified_payment_settles_once():
    payment = tx(provider_reference="cs_test_payment", status="processing")
    event = stored_stripe_event()
    with patch("txcore.workers.webhooks.client") as provider:
        provider.return_value.v1.checkout.sessions.retrieve.return_value = provider_session(payment)
        assert process_webhooks.run() == {"processed": 1}
        assert process_webhooks.run() == {"processed": 0}
    payment.refresh_from_db()
    event.refresh_from_db()
    assert payment.status == "settled"
    assert event.status == "processed"
    assert OutboxEvent.objects.filter(payload__event="payment_settled").count() == 1


def test_wrong_provider_amount_never_settles():
    payment = tx(provider_reference="cs_test_payment", status="processing")
    event = stored_stripe_event()
    session = provider_session(payment)
    session.amount_total = 999
    with patch("txcore.workers.webhooks.client") as provider:
        provider.return_value.v1.checkout.sessions.retrieve.return_value = session
        process_webhooks.run()
    payment.refresh_from_db()
    event.refresh_from_db()
    assert payment.status == "processing"
    assert event.status == "failed"


def test_provider_outage_retains_webhook_for_retry():
    event = stored_stripe_event()
    with patch("txcore.workers.webhooks.client", side_effect=ConnectionError("unavailable")):
        process_webhooks.run()
    event.refresh_from_db()
    assert event.status == "received"
    assert event.retry_count == 1
    assert event.next_attempt_at > timezone.now()


def test_simulation_cannot_settle_a_stripe_transaction():
    payment = tx()
    process_settlement.run(str(payment.id))
    payment.refresh_from_db()
    assert payment.status == "pending"


def test_outbox_retains_event_until_acknowledged():
    event = OutboxEvent.objects.create(
        event_key="one", topic="transactions", aggregate_id="one", payload={"event": "test"}
    )
    with patch("txcore.workers.delivery.publish", return_value=False):
        assert deliver_outbox.run() == {"delivered": 0}
    event.refresh_from_db()
    assert event.published_at is None
    assert event.attempts == 1
    OutboxEvent.objects.filter(pk=event.pk).update(available_at=timezone.now())
    with patch("txcore.workers.delivery.publish", return_value=True) as publish:
        assert deliver_outbox.run() == {"delivered": 1}
        assert deliver_outbox.run() == {"delivered": 0}
    publish.assert_called_once()
    assert publish.call_args.args[2]["event_id"] == str(event.id)


def test_currency_and_duplicate_discrepancies_are_visible():
    payment = tx()
    run = ReconciliationRun.objects.create(filename="currency.csv")
    result = run_reconciliation(
        run,
        "reference,amount,currency,status\n"
        f"{payment.reference},25.00,EUR,pending\n"
        f"{payment.reference},25.00,USD,pending\n",
    )
    assert result.discrepancies == 2
    assert set(run.discrepancy_set.values_list("discrepancy_type", flat=True)) == {
        "currency_mismatch",
        "duplicate",
    }
    mismatch = run.discrepancy_set.get(discrepancy_type="currency_mismatch")
    assert (mismatch.expected_currency, mismatch.actual_currency) == ("EUR", "USD")


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-1", "1000000000000000", "1.00001"])
def test_invalid_statement_amount_is_skipped(amount):
    run = ReconciliationRun.objects.create(filename="invalid.csv")
    result = run_reconciliation(run, f"reference,amount,currency\nTXN-invalid,{amount},USD\n")
    assert result.status == "completed"
    assert result.skipped == 1


def test_row_limit_fails_with_no_partial_discrepancies():
    run = ReconciliationRun.objects.create(filename="too-many.csv")
    with override_settings(MAX_RECONCILIATION_ROWS=1):
        result = run_reconciliation(run, "reference,amount,currency\na,1,USD\nb,1,USD\n")
    assert result.status == "failed"
    assert not ReconciliationDiscrepancy.objects.filter(run=run).exists()


def test_failed_statement_returns_422(api):
    file = SimpleUploadedFile("invalid.csv", b"wrong,headers\nvalue,1", content_type="text/csv")
    assert api.post("/api/v1/reconciliation/upload/", {"file": file}, format="multipart").status_code == 422


def test_large_statement_rejected_before_run_creation(api):
    file = SimpleUploadedFile("large.csv", b"x" * 21)
    with override_settings(MAX_RECONCILIATION_BYTES=20):
        assert (
            api.post("/api/v1/reconciliation/upload/", {"file": file}, format="multipart").status_code == 413
        )
    assert not ReconciliationRun.objects.exists()


def test_database_metrics_include_worker_written_state():
    from txcore.core.metrics import DatabaseMetricsCollector

    tx(status="settled")
    samples = [sample for family in DatabaseMetricsCollector().collect() for sample in family.samples]
    assert any(
        s.name == "txcore_transaction_state" and s.labels["status"] == "settled" and s.value == 1
        for s in samples
    )


def test_demo_setup_is_repeatable_without_resetting_password():
    from django.core.management import call_command

    with override_settings(DEBUG=True):
        call_command("setup_demo")
        user = get_user_model().objects.get(username="demo.admin")
        user.set_password("changed-password")
        user.save()
        call_command("setup_demo")
    user.refresh_from_db()
    assert user.check_password("changed-password")


def test_provider_precision_rejected_before_transaction_creation(api):
    assert create(api, amount="25.001").status_code == 422
    assert not Transaction.objects.exists()


def test_token_authentication_accesses_private_api(operator):
    client = APIClient()
    response = client.post(
        "/api/token/", {"username": operator.username, "password": "password"}, format="json"
    )
    assert response.status_code == 200
    client.credentials(HTTP_AUTHORIZATION="Token " + response.data["token"])
    assert client.get("/api/v1/transactions/").status_code == 200


def test_missed_webhook_is_recovered_from_provider_state():
    from txcore.workers.webhooks import recover_provider_payments

    payment = tx(status="processing", provider_reference="cs_test_payment")
    with patch("txcore.workers.webhooks.client") as provider:
        provider.return_value.v1.checkout.sessions.retrieve.return_value = provider_session(payment)
        assert recover_provider_payments.run() == {"recovered": 1}
        assert recover_provider_payments.run() == {"recovered": 0}
    payment.refresh_from_db()
    assert payment.status == "settled"
    assert OutboxEvent.objects.count() == 1


def test_provider_recovery_outage_leaves_payment_pending():
    from txcore.workers.webhooks import recover_provider_payments

    payment = tx(status="processing", provider_reference="cs_test_payment")
    with patch("txcore.workers.webhooks.client", side_effect=ConnectionError("unavailable")):
        assert recover_provider_payments.run() == {"recovered": 0}
    payment.refresh_from_db()
    assert payment.status == "processing"
    assert not OutboxEvent.objects.exists()

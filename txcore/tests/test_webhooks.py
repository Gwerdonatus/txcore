import json
import pytest
from rest_framework.test import APIClient
from unittest.mock import patch

from txcore.apps.webhooks.models import WebhookEvent
from txcore.apps.webhooks.signature import compute_signature, validate_signature


@pytest.fixture(autouse=True)
def enable_local_demo(settings):
    settings.DEBUG = True


@pytest.fixture
def client(db):
    from django.contrib.auth import get_user_model
    user = get_user_model().objects.create_user(username="operator", password="test-password", is_staff=True)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def webhook_payload():
    return {
        "event_type": "payment.success",
        "reference": "TXN-WEBHOOK001",
        "data": {"amount": "100.00", "currency": "USD"},
    }


@pytest.mark.django_db
class TestWebhookIngest:
    def test_valid_signature_accepted(self, client, webhook_payload):
        body = json.dumps(webhook_payload).encode()
        signature = compute_signature(body)

        with patch("txcore.apps.webhooks.views.enqueue", return_value=True):
            response = client.post(
                "/api/v1/webhooks/ingest/demo/",
                data=body,
                content_type="application/json",
                HTTP_X_WEBHOOK_SIGNATURE=signature,
            )

        assert response.status_code == 202
        data = response.json()
        assert data["received"] is True
        assert "event_id" in data

    def test_invalid_signature_rejected(self, client, webhook_payload):
        body = json.dumps(webhook_payload).encode()
        response = client.post(
            "/api/v1/webhooks/ingest/demo/",
            data=body,
            content_type="application/json",
            HTTP_X_WEBHOOK_SIGNATURE="invalid-signature",
        )
        assert response.status_code == 401

    def test_missing_signature_rejected(self, client, webhook_payload):
        body = json.dumps(webhook_payload).encode()
        response = client.post(
            "/api/v1/webhooks/ingest/demo/",
            data=body,
            content_type="application/json",
        )
        assert response.status_code == 401

    def test_invalid_json_rejected(self, client):
        body = b"not-valid-json{"
        signature = compute_signature(body)
        response = client.post(
            "/api/v1/webhooks/ingest/demo/",
            data=body,
            content_type="application/json",
            HTTP_X_WEBHOOK_SIGNATURE=signature,
        )
        assert response.status_code == 400

    def test_event_stored_in_db(self, client, webhook_payload):
        body = json.dumps(webhook_payload).encode()
        signature = compute_signature(body)

        with patch("txcore.apps.webhooks.views.enqueue", return_value=True):
            client.post(
                "/api/v1/webhooks/ingest/demo/",
                data=body,
                content_type="application/json",
                HTTP_X_WEBHOOK_SIGNATURE=signature,
            )

        event = WebhookEvent.objects.get(provider="demo")
        assert event.event_type == "payment.success"
        assert event.status == WebhookEvent.Status.RECEIVED

    def test_transaction_reference_extracted(self, client, webhook_payload):
        body = json.dumps(webhook_payload).encode()
        signature = compute_signature(body)

        with patch("txcore.apps.webhooks.views.enqueue", return_value=True):
            client.post(
                "/api/v1/webhooks/ingest/demo/",
                data=body,
                content_type="application/json",
                HTTP_X_WEBHOOK_SIGNATURE=signature,
            )

        event = WebhookEvent.objects.latest("received_at")
        assert event.transaction_reference == "TXN-WEBHOOK001"


class TestSignatureValidation:
    def test_valid_signature(self):
        payload = b'{"test": "data"}'
        sig = compute_signature(payload)
        assert validate_signature(payload, sig) is True

    def test_tampered_payload(self):
        original = b'{"amount": "100"}'
        sig = compute_signature(original)
        tampered = b'{"amount": "999"}'
        assert validate_signature(tampered, sig) is False

    def test_stripe_style_prefix(self):
        payload = b'{"event": "test"}'
        sig = compute_signature(payload)
        stripe_sig = f"sha256={sig}"
        assert validate_signature(payload, stripe_sig) is True

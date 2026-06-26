"""
TxCore Load Test
================
Run with: locust -f locustfile.py --host=http://localhost:8000

Simulates realistic payment traffic:
- 70% transaction creation
- 20% webhook delivery
- 10% transaction lookup

Target: 1000+ concurrent users without error rate above 1%
"""
import json
import uuid
import hashlib
import hmac
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner


WEBHOOK_SECRET = "local-webhook-secret"


def compute_signature(payload_bytes: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), payload_bytes, hashlib.sha256).hexdigest()


class PaymentUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        self.created_references = []

    @task(7)
    def create_transaction(self):
        idempotency_key = f"locust-{uuid.uuid4().hex}"
        payload = {
            "amount": str(round(10 + uuid.uuid4().int % 10000 / 100, 2)),
            "currency": "USD",
            "description": "Locust load test payment",
            "provider": "stripe",
        }
        with self.client.post(
            "/api/v1/transactions/create/",
            json=payload,
            headers={"Idempotency-Key": idempotency_key},
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                data = response.json()
                self.created_references.append(data.get("reference"))
                response.success()
            else:
                response.failure(f"Transaction create failed: {response.status_code}")

    @task(2)
    def ingest_webhook(self):
        payload = {
            "event_type": "payment.success",
            "reference": f"TXN-{uuid.uuid4().hex[:8].upper()}",
            "data": {"amount": "100.00", "currency": "USD"},
        }
        body = json.dumps(payload).encode()
        signature = compute_signature(body)

        with self.client.post(
            "/api/v1/webhooks/ingest/stripe/",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": signature,
            },
            catch_response=True,
        ) as response:
            if response.status_code == 202:
                response.success()
            else:
                response.failure(f"Webhook ingest failed: {response.status_code}")

    @task(1)
    def get_transaction(self):
        if not self.created_references:
            return
        reference = self.created_references[-1]
        with self.client.get(
            f"/api/v1/transactions/{reference}/",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Transaction GET failed: {response.status_code}")


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    if isinstance(environment.runner, MasterRunner):
        print("TxCore load test initialised — target: 1000+ concurrent users")

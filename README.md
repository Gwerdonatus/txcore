# TxCore

**High-throughput distributed payment processing system built with Django, Celery, Kafka, PostgreSQL, and Redis.**

A production-grade backend demonstrating the core patterns used by payment platforms at scale: idempotent transaction APIs, HMAC-validated webhook ingestion, event-driven async workers, CSV financial reconciliation, and full observability with Prometheus and Grafana.

---

## Architecture

```
┌─────────────────────────────────────────────┐
│              External Clients               │
│         Mobile · Web · Partner APIs         │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│         Nginx  (rate limiter · TLS)         │
│              100 req/s per IP               │
└──────┬──────────┬──────────────┬────────────┘
       │          │              │
┌──────▼──┐  ┌───▼────┐  ┌─────▼──────┐
│Transaction│  │Webhook │  │Reconcilia- │
│   API    │  │Service │  │tion Service│
│(DRF+idem)│  │(HMAC)  │  │(CSV engine)│
└──────┬──┘  └───┬────┘  └─────┬──────┘
       │          │              │
┌──────▼──────────▼──────────────▼──────────┐
│               Kafka Event Bus              │
│  txcore.transactions · txcore.webhooks     │
│  txcore.alerts                             │
└──────┬──────────┬──────────────────────────┘
       │          │
┌──────▼──┐  ┌───▼──────┐  ┌──────────────┐
│Settlement│  │Reconcile │  │Alert Worker  │
│ Worker  │  │ Worker   │  │(SLA timers)  │
│(Celery) │  │(Celery)  │  │(Celery Beat) │
└──────┬──┘  └───┬──────┘  └──────┬───────┘
       │          │                │
┌──────▼──────────▼────────────────▼──────┐
│                 Storage                  │
│  PostgreSQL (primary) · Redis (cache,    │
│  broker, idempotency keys)               │
└──────────────────┬───────────────────────┘
                   │
┌──────────────────▼───────────────────────┐
│              Observability               │
│   Prometheus /metrics · Grafana :3000    │
│   Locust load test (1000+ concurrent)    │
└──────────────────────────────────────────┘
```

---

## What this demonstrates

| Pattern | Implementation |
|---|---|
| Idempotent APIs | Redis-backed idempotency keys prevent duplicate transactions |
| HMAC webhook validation | SHA-256 signature verification on all inbound webhooks |
| Event-driven architecture | Kafka topics decouple services from workers |
| Async task processing | Celery workers with exponential backoff retry |
| Financial reconciliation | CSV → DB matching engine with discrepancy detection |
| N+1 query prevention | `select_related`, `prefetch_related`, bulk DB operations |
| Observability | Custom Prometheus metrics, Grafana dashboards |
| Quality engineering | Pytest suite with >80% coverage, CI/CD via GitHub Actions |
| High-concurrency design | Nginx rate limiting, 4-worker Gunicorn, connection pooling |

---

## Tech stack

- **Backend:** Python 3.12, Django 4.2, Django REST Framework
- **Async tasks:** Celery 5.3, Redis broker
- **Event streaming:** Apache Kafka
- **Database:** PostgreSQL 16
- **Cache / idempotency store:** Redis 7
- **Observability:** Prometheus, Grafana
- **Load testing:** Locust
- **Infrastructure:** Docker, Docker Compose, Nginx, GitHub Actions CI/CD

---

## Quickstart

### Prerequisites
- Docker and Docker Compose installed
- Python 3.12+ (for running tests locally)

### 1. Clone and configure

```bash
git clone https://github.com/YOUR_USERNAME/txcore.git
cd txcore
cp .env.example .env
```

### 2. Start all services

```bash
docker-compose up --build
```

This starts: PostgreSQL, Redis, Kafka, Zookeeper, Django app, Celery worker, Prometheus, Grafana.

Wait ~30 seconds for all services to be healthy, then:

```bash
# Run migrations
docker-compose exec web python manage.py migrate

# Seed sample data (optional — good for demos)
docker-compose exec web python scripts/seed.py
```

### 3. Verify everything is running

| Service | URL |
|---|---|
| API | http://localhost:8000/api/v1/ |
| API docs (Swagger) | http://localhost:8000/api/docs/ |
| Prometheus metrics | http://localhost:8000/metrics |
| Prometheus UI | http://localhost:9090 |
| Grafana | http://localhost:3000 (admin / admin) |

---

## API Reference

### Transactions

#### Create a transaction
```bash
POST /api/v1/transactions/create/
Headers:
  Idempotency-Key: <unique-key>
  Content-Type: application/json

Body:
{
  "amount": "250.00",
  "currency": "USD",
  "description": "Payment for order #1042",
  "provider": "stripe"
}
```

Response `201 Created`:
```json
{
  "id": "a3f8c2d1-...",
  "reference": "TXN-4A8B2C1D3E",
  "amount": "250.0000",
  "currency": "USD",
  "status": "pending",
  "provider": "stripe",
  "created_at": "2025-06-01T10:23:41Z"
}
```

Re-send with the same `Idempotency-Key` → returns `200 OK` with the original response. No duplicate transaction created.

#### Get transaction
```bash
GET /api/v1/transactions/TXN-4A8B2C1D3E/
```

#### List transactions
```bash
GET /api/v1/transactions/?status=pending&currency=USD
```

---

### Webhooks

#### Ingest a webhook
```bash
POST /api/v1/webhooks/ingest/<provider>/
Headers:
  X-Webhook-Signature: <hmac-sha256-hex>
  Content-Type: application/json

Body:
{
  "event_type": "payment.success",
  "reference": "TXN-4A8B2C1D3E",
  "data": { "amount": "250.00", "currency": "USD" }
}
```

Response `202 Accepted`:
```json
{ "received": true, "event_id": "b9e1a..." }
```

Invalid or missing signature → `401 Unauthorized`.

#### Generate a valid test signature
```bash
python3 -c "
import hmac, hashlib, json
payload = json.dumps({'event_type': 'payment.success', 'reference': 'TXN-TEST'}).encode()
sig = hmac.new(b'local-webhook-secret', payload, hashlib.sha256).hexdigest()
print(sig)
"
```

---

### Reconciliation

#### Upload a CSV for reconciliation
```bash
POST /api/v1/reconciliation/upload/
Content-Type: multipart/form-data
Body: file=@bank_statement.csv
```

CSV format:
```csv
reference,amount,currency,status
TXN-4A8B2C1D3E,250.00,USD,settled
TXN-9K2M1P0Q8R,100.00,EUR,settled
```

Response `201 Created`:
```json
{
  "run_id": "c4d7...",
  "status": "completed",
  "total_rows": 2,
  "matched": 1,
  "discrepancies": 1,
  "skipped": 0
}
```

#### Get discrepancy detail
```bash
GET /api/v1/reconciliation/<run_id>/
```

---

## Running tests

### Local (without Docker)

```bash
# Install dependencies
pip install -r requirements.txt

# Set test environment variables
export DEBUG=True
export SECRET_KEY=test-secret-key
export WEBHOOK_SECRET=test-webhook-secret
export DB_HOST=localhost
export DB_NAME=txcore_test
export DB_USER=txcore
export DB_PASSWORD=txcore
export REDIS_URL=redis://localhost:6379/0
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Run migrations
python manage.py migrate

# Run tests with coverage
pytest
```

### Inside Docker

```bash
docker-compose exec web pytest
```

### Expected output

```
======= test session starts =======
txcore/tests/test_transactions.py::TestTransactionCreate::test_creates_transaction_successfully PASSED
txcore/tests/test_transactions.py::TestTransactionCreate::test_idempotency_returns_same_response PASSED
txcore/tests/test_transactions.py::TestTransactionCreate::test_missing_idempotency_key_returns_400 PASSED
...
txcore/tests/test_webhooks.py::TestWebhookIngest::test_valid_signature_accepted PASSED
txcore/tests/test_webhooks.py::TestWebhookIngest::test_invalid_signature_rejected PASSED
...
txcore/tests/test_reconciliation.py::TestReconciliationEngine::test_all_matched PASSED
txcore/tests/test_reconciliation.py::TestReconciliationEngine::test_detects_amount_mismatch PASSED
...

---------- coverage: 83% -----------
31 passed in 4.2s
```

---

## Load testing

```bash
# Start the stack
docker-compose up -d

# Run the load test
locust -f locustfile.py --host=http://localhost:8000

# Or headless (1000 users, 10s ramp-up, 60s duration)
locust -f locustfile.py --host=http://localhost:8000 \
  --users 1000 --spawn-rate 10 --run-time 60s --headless
```

Open the Locust web UI at http://localhost:8089 to watch real-time throughput, response times, and error rates.

### What the load test covers
- **70%** — `POST /api/v1/transactions/create/` with unique idempotency keys
- **20%** — `POST /api/v1/webhooks/ingest/stripe/` with valid HMAC signatures
- **10%** — `GET /api/v1/transactions/<reference>/` lookups

---

## API smoke test

```bash
# Make sure the stack is running, then:
bash scripts/test_api.sh
```

Runs 7 curl-based checks covering transaction creation, idempotency, webhook validation, and metrics.

---

## Observability

### Prometheus metrics (custom)

| Metric | Type | Description |
|---|---|---|
| `txcore_transactions_created_total` | Counter | Transactions created, labelled by currency and status |
| `txcore_transaction_amount` | Histogram | Distribution of transaction amounts |
| `txcore_webhooks_received_total` | Counter | Webhooks received by provider and event type |
| `txcore_webhook_validation_failures_total` | Counter | HMAC validation failures by provider |
| `txcore_reconciliation_runs_total` | Counter | Reconciliation jobs completed or failed |
| `txcore_reconciliation_discrepancies` | Gauge | Current unresolved discrepancies |
| `txcore_celery_tasks_processed_total` | Counter | Celery tasks by name and status |
| `txcore_celery_task_duration_seconds` | Histogram | Worker execution time |

### Grafana

Access at http://localhost:3000 (admin / admin).

Import the dashboard from `grafana/dashboards/` or build your own panels using the metrics above.

---

## Design decisions

### Why idempotency keys?
Payment APIs must be safe to retry. If a client times out after sending a request, they don't know if the transaction was created. Idempotency keys (stored in Redis with a 24-hour TTL) guarantee that retrying the same request returns the original response without creating a duplicate transaction. This is the same pattern used by Stripe, PayPay, and Paystack.

### Why Kafka over direct Celery tasks?
Celery tasks called directly from views couple the API response time to the task broker's availability. Kafka decouples them: the API publishes an event and returns immediately; workers consume at their own pace and can be scaled independently. This also provides a durable event log — if a worker crashes, the event is not lost.

### Why bulk_create in the reconciliation engine?
Inserting discrepancies one at a time inside a loop is a classic N+1 write problem. `bulk_create()` batches all inserts into a single SQL statement, which is significantly faster at scale (a 10,000-row CSV produces one INSERT rather than thousands).

### Why HMAC-SHA256 for webhooks?
Webhook endpoints are public URLs. Without signature validation, anyone can POST fake events. HMAC-SHA256 with a shared secret (known only to you and the provider) proves the payload came from the correct source and was not tampered with in transit. This is the standard used by Stripe, Paystack, and Flutterwave.

---

## Project structure

```
txcore/
├── txcore/
│   ├── apps/
│   │   ├── transactions/    # Transaction API + idempotency
│   │   ├── webhooks/        # Webhook ingestion + HMAC validation
│   │   └── reconciliation/  # CSV matching engine
│   ├── workers/
│   │   ├── settlement.py    # Async settlement with retry
│   │   └── alerts.py        # SLA breach detection
│   ├── events/
│   │   └── kafka_producer.py
│   ├── core/
│   │   ├── idempotency.py
│   │   ├── metrics.py
│   │   └── exceptions.py
│   └── tests/
│       ├── test_transactions.py
│       ├── test_webhooks.py
│       └── test_reconciliation.py
├── nginx/nginx.conf
├── prometheus/prometheus.yml
├── grafana/dashboards/
├── scripts/
│   ├── seed.py
│   └── test_api.sh
├── locustfile.py
├── docker-compose.yml
├── Dockerfile
├── pytest.ini
└── requirements.txt
```

---

## CI/CD

GitHub Actions pipeline (`.github/workflows/ci.yml`):

1. **Test** — spins up Postgres + Redis services, runs full Pytest suite with coverage check (fails if <80%)
2. **Lint** — runs flake8
3. **Build** — on merge to `main`, builds Docker image and pushes to GitHub Container Registry (GHCR)

---

## Author

**Donatus Gwer** — Backend Engineer  
[github.com/Gwerdonatus](https://github.com/Gwerdonatus) · [linkedin.com/in/donatus-gwer](https://linkedin.com/in/donatus-gwer) · donatusgwer@gmail.com

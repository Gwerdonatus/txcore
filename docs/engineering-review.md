# Engineering review

Reviewed the application, worker modules, schema, Compose setup, test configuration and CI workflow on 9 October 2026.

## Positioning

TxCore is a backend prototype with a useful combination of retry handling, webhook verification and reconciliation. It is appropriate to discuss as a solo engineering case study. The source does not support the previous README's claims of production-grade operation, measured high throughput or Kafka-driven settlement. The rewritten README presents concrete behavior and distinguishes the implemented paths from future architecture.

## Changes made during the walkthrough

| Finding | Change |
|---|---|
| Local ports collided with Sentinel | Loopback-only, configurable API/Kafka/monitoring ports; private PostgreSQL/Redis ports |
| Fresh API containers lacked migrated tables and mounted static assets | Run migrations and static collection before Gunicorn; verify the schema endpoint for readiness |
| Worker modules were outside Celery's default `tasks.py` discovery | Explicitly register the settlement and SLA modules |
| Expired Redis entries made a repeated unique transaction key raise a database error | Use database `get_or_create` as the durable fallback; add a cache-eviction retry regression |
| OpenAPI omitted webhook headers and CSV upload/response shapes | Describe the actual existing API contracts with serializers and annotations |
| Random seed data did not prove an ingestion workflow | Add an asserted local HTTP demonstration and a separate explicit Celery dispatch demonstration |
| Kafka 2.0.2 failed to import on the Python 3.12 runtime | Pin 2.0.6; verify an actual acknowledged broker send and add a CI import check |
| Coverage included test files and delivery paths lacked regressions | Exclude test and migration files; add producer acknowledgement, failure and worker execution tests |
| Documentation described features not present | Correct the architecture, provider signature description, test environment and operational claims |

## Design tradeoffs to explain in an interview

**Idempotency.** Redis reduces the cost of sequential retries; the database unique key controls record duplication. The fallback prevents a cache miss from creating a second record or raising a uniqueness error. The same key with different bodies is not rejected using a fingerprint, and there is no tenant/caller scope. Recovering the record does not establish exactly-once event publication.

**Kafka.** The producer waits for acknowledgement and reports failure, but views do not turn that failure into a durable retry intent. There is no outbox or consumer. The project currently demonstrates publication, not an event-driven settlement pipeline. Adding Kafka is not justified by a measured throughput requirement; simpler direct task dispatch would be appropriate for a smaller deployment.

**Settlement.** The worker moves a synthetic record from pending to processing to settled. It does not call a provider. Its retry behavior after a failure in processing needs a recoverable state machine and provider idempotency before real use. The demo queues the task explicitly; webhook acceptance is not wired to it.

**Reconciliation.** The engine batch-fetches referenced transactions and batch-inserts discrepancies, reducing per-row database queries. It flags the first applicable discrepancy for each row. Currency comparison, duplicate-row handling, bounded uploads, durable job scheduling and streaming larger files remain work. The demonstration deliberately uses USD for all statement rows.

**Webhook security.** Constant-time comparison validates a generic shared-secret HMAC over raw bytes. Provider names are labels; this is not Stripe's timestamped signing format. Replay/freshness enforcement and per-provider secrets are absent. Accepted reports remain stored as received; there is no processing consumer.

**Observability.** Prometheus can scrape API request and application metrics. Counters modified in a separate Celery process are not exported by the API automatically. Compose uses one Gunicorn process for coherent demonstration counters; this is not evidence of scale. Grafana starts, but no application dashboard is provisioned. The Nginx configuration is not included as a Compose service.

## Verification interpretation

Tests run with `txcore.test_settings`: SQLite in memory and a local-memory cache. CI starts PostgreSQL and runs migrations there, but pytest's database remains SQLite. Kafka calls in API tests are mocked. Actual local HTTP outcomes, Redis cache behavior, worker execution, Kafka acknowledgements and PostgreSQL persistence therefore require separate runtime checks. Those results are recorded in [verification.md](verification.md).

The Locust script and a CI badge are useful tooling, not measured performance or assurance of secure deployment. The local APIs use `AllowAny`; host access is loopback-only in this demonstration.

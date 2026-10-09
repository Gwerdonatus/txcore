# Verification evidence

Verified locally on an Apple Silicon Mac on 9 October 2026 using Docker Compose project `txcore`. All application data is synthetic; no funds moved or payment provider was contacted.

## Automated checks

- **42 tests passed**, with **92.13% application statement coverage**: 635 statements, 50 missed. `.coveragerc` excludes tests, migrations and test settings. The 80% coverage gate remains enabled.
- Django system checks: no issues.
- Migration drift check: no changes detected.
- OpenAPI validation with `--validate --fail-on-warn`: no warnings or errors.
- flake8: checked against CI's 110-character line limit.
- Compose configuration validated, and API/worker images built locally with Python 3.12 and `kafka-python==2.0.6`.

Tests use SQLite and an in-memory cache. API tests mock Kafka; producer and worker tests exercise acknowledgement, failures, simulated settlement and SLA selection with controlled dependencies. They do not prove PostgreSQL concurrency, a live provider integration or durable event delivery. CI additionally runs PostgreSQL migrations and validates startup imports and the API schema.

## Actual HTTP demonstration

`scripts/demo.py` asserts these outcomes against the running PostgreSQL/Redis-backed API:

| Check | Observed result |
|---|---|
| Create three synthetic transactions | 201 for each first creation |
| Repeat each idempotency key | 200, same transaction IDs |
| Run the whole demonstration again | Existing transaction IDs reused; no additional transaction records |
| Valid generic HMAC webhook | 202 and stored report |
| Invalid signature | 401 |
| Four-row CSV statement | Completed: 1 match, 3 discrepancies, 0 skipped |
| Discrepancy details | Amount mismatch, status mismatch, missing transaction |

Repeating the script intentionally creates another accepted webhook report and another reconciliation run. Only transaction intake is asserted to be idempotent.

## Runtime checks

Eight Compose services started: PostgreSQL, Redis, ZooKeeper, Kafka, API, Celery worker, Prometheus and Grafana. PostgreSQL, Redis, Kafka, API and worker have configured health checks; the remaining services were verified through running state and HTTP responses where applicable.

- An actual Kafka publication returned `True` after broker acknowledgement.
- `scripts/demo_settlement.py` dispatched a task through Redis to Celery and observed the synthetic EUR record become `settled` in PostgreSQL. Repeating it reuses the record.
- Prometheus displayed its API target as **UP (1/1)**.
- Swagger, API schema, metrics, Prometheus readiness and Grafana health endpoints responded successfully.

The real browser captures are in [screenshots](screenshots/README.md). The API is available locally at http://localhost:8100/api/docs/.

## Scope

There is no Kafka consumer, transactional outbox, live payment integration, customer dashboard or provisioned Grafana dashboard. No throughput or p95 latency benchmark was run. Authentication, currency reconciliation and production hardening remain documented engineering work.

Pull-request CI runs tests and lint. The image publishing job is intentionally limited to `main`; a skipped publishing job on this PR is expected. See the PR checks for the latest remote result.

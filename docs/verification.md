# Verification evidence

Verified locally on an Apple Silicon Mac on **9 October 2026**, using the actual Compose application, PostgreSQL 16, Redis, Kafka, Celery and Stripe test mode. Screenshots are actual browser captures with staged demo data.

## Automated checks

| Check | Observed result |
|---|---|
| PostgreSQL test suite | 88 passed, including two real concurrent request tests |
| SQLite coverage suite | 86 passed; 2 PostgreSQL-specific tests skipped |
| Application coverage | 91.34%, 993 statements, 86 missed |
| Flake8 | Passed, 110-character limit, migrations excluded |
| Django system check | No issues |
| Migration drift | No changes detected |
| OpenAPI validation | Passed with warnings treated as failure |
| Compose configuration | Core and Stripe profile validated |

Tests isolate their databases and mock external provider/network behavior. PostgreSQL concurrency tests run four parallel callers and verify one transaction/outbox event and one initialized Checkout session. Coverage excludes tests, migrations and test settings. CI runs both suites; see [the latest workflow](https://github.com/Gwerdonatus/txcore/actions/workflows/ci.yml).

## Actual provider workflow

A browser completed **USD 3.00** through Stripe-hosted Checkout using public test card data. The resulting TxCore reference was **TXN-051F59C503CF**. Stripe's listener delivered `checkout.session.completed` event **evt_1UORv7Rwkn46vgfARyyz71RX** with HTTP **202**. The stored receipt became `processed`, its error was empty, and the transaction became `settled` after provider verification.

Earlier USD 5.00 and USD 25.00 tests exposed an internal-host allowlist error. That configuration was corrected to allow `web` without wildcarding the host list. The first test was verified through a locally re-signed provider event; the second recovered through the provider-state scanner. The USD 3.00 run establishes fresh automatic webhook delivery after the fix. No real funds moved.

Other integration fixes were exercised against the actual SDK: dynamic payment methods for current Checkout behavior, stable versioned provider idempotency keys and recursive SDK event conversion before persistence.

## Local simulation and reconciliation

The asserted HTTP script ran twice. Transaction retries returned HTTP 200 and reused the same three records. Valid demo signatures returned 202; invalid ones returned 401. Each four-row CSV produced one match, three discrepancies and zero skipped rows. Webhook processing completed through Beat/worker.

A separate six-row synthetic statement uses real local references, one match and five deliberate differences: amount, currency, status, missing reference and duplicate reference. It is comparison evidence, not an actual Stripe payout statement.

## Kafka outage recovery

With the TxCore Kafka service deliberately stopped, intake still created **TXN-B1491014385B** and retained outbox event **6511cb6b-a96c-44a2-b12d-d793f71d3d8f** after failed acknowledgement. The broker was restarted, and the same durable event was acknowledged after recovery (three delivery attempts). No core service was removed or health check disabled. This is a local failure/recovery test, not a high-availability claim.

## Runtime scope

The core stack has nine services; the Stripe listener makes ten. Database, Redis, Kafka, API and worker expose configured health checks. Beat schedules durable processing, provider recovery and delivery. Prometheus scrapes the internal API, and Grafana's provisioned dashboard reads database-backed payment/outbox/webhook gauges.

No load-test throughput, p95 latency, live payment, bank settlement, public deployment or production-readiness result is claimed. The main-branch image-push job is intentionally skipped for pull requests. See [engineering boundaries](engineering-review.md).

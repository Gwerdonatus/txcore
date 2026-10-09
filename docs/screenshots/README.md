# Screenshot provenance

Captured from the actual local TxCore prototype on 9 October 2026. These are unaltered browser screenshots of Swagger/OpenAPI, Django REST Framework's browsable API and Prometheus. No product dashboard, transaction or performance figure was generated for the images.

## Scenario

The asserted HTTP demo uses three synthetic USD transactions (250, 120 and 80), fixed retry keys, a generic signed webhook and a four-row CSV statement. The statement produces one match and three discrepancies: amount mismatch, status mismatch and missing transaction.

A separate EUR record is settled by an explicitly dispatched Celery task. That task changes local database state without contacting a provider. All transaction metadata marks the data as synthetic and states that no external action was performed.

The demo is not affiliated with any payment provider. The `demo` provider name is a local label. Webhook acceptance remains `received`; it is not proof of payment or automatic settlement. Idempotency assertions and HTTP status checks are in [scripts/demo.py](../../scripts/demo.py), not inferred from screenshots.

| Screenshot | What it shows |
|---|---|
| [API documentation](api-docs.jpg) | The live OpenAPI contract |
| [Transaction detail](transaction-detail.jpg) | Actual stored synthetic transaction fields |
| [Transactions](transactions.jpg) | Transaction list filtered to the simulated EUR settlement |
| [Webhook reports](webhooks.jpg) | Persisted accepted generic signed report |
| [Reconciliation detail](reconciliation-detail.jpg) | Actual expected/actual differences and missing reference |
| [Reconciliation history](reconciliation-runs.jpg) | Completed four-row CSV runs |
| [Prometheus](prometheus.jpg) | Successful scrape of the running API |

Measurements and caveats are in [verification.md](../verification.md). See [local-demo.md](../local-demo.md) to reproduce the HTTP workflow. Screenshots are snapshots, not production usage or load-test evidence.

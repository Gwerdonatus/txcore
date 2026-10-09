# Engineering decisions and boundaries

TxCore is a single-workspace Stripe payment operations sandbox. Its core concern is preserving meaning across retries, provider notifications and conflicting statements.

## Database-first intake

A unique SHA-256 key scopes the caller's idempotency key to their account. A fingerprint covers validated defaults, normalized decimal amount, currency, description, provider and metadata. An identical retry returns current state; a changed body returns 409. PostgreSQL's uniqueness resolves concurrent intake. A transaction and its creation outbox event commit together. Older records are preserved by additive migrations; the new scoped key contract does not retroactively re-key old prototype records.

Checkout initialization locks one transaction. Stripe receives `checkout-v1-{transaction UUID}`, and TxCore stores the returned session and URL. Retrying after provider success but before local commit can recover the same session through Stripe's idempotency behavior. This is not an unlimited guarantee: provider idempotency retention is finite. A production design would track ambiguous requests and investigate before creating a replacement session.

## Payment evidence

A browser redirect is a navigation event, not payment evidence. The Stripe SDK verifies timestamped signatures over raw bytes with a 300-second tolerance. Live keys, live sessions and live webhook events are rejected. Events deduplicate by provider event ID. Processing retrieves current Stripe state and compares the stored provider session, client reference, amount and currency before applying `settled`.

Receipts persist before 202, independently of Redis or task dispatch. Beat polls for work. Provider failures retry with backoff; after five attempts the receipt is marked failed for review. A separate 60-second scanner checks processing Stripe payments to recover missed webhooks. Its batch is 20 records; a large pending backlog needs fair scheduling and pagination before scale. No fake receipt is created by recovery.

`settled` means Stripe reports a paid, complete test Checkout session. It does not mean a bank payout settled. Local HMAC demo events are DEBUG-only and cannot settle Stripe transactions. The explicit simulation settlement task also refuses Stripe records.

## Why the outbox and Kafka coexist

The outbox solves the database/event dual-write gap. The relay marks delivery only after Kafka acknowledges it, retaining failed attempts and applying backoff. If Kafka accepts an event and the database commit fails, the event may be published again. Stable event IDs make downstream deduplication possible; exactly-once delivery is not claimed.

Kafka is an integration stream for independently operated consumers. There is no consumer in this repository and no claim that Kafka drives settlement. For a smaller system, PostgreSQL outbox plus Celery alone is simpler. Kafka's inclusion is a deliberate event-delivery exercise, not a demonstrated performance requirement.

## Statement interpretation

CSV processing is synchronous and bounded to 2 MiB and 10,000 rows. One reference lookup avoids per-row database queries; discrepancies are inserted in a batch with the completed counts. Required columns are reference, amount and currency; status is optional. Invalid rows are counted as skipped. Valid duplicate references, missing records, currency differences, amount differences and status differences are recorded.

Each valid row produces the first applicable discrepancy, rather than multiple overlapping flags. Currency comparison precedes amount comparison. Decimal amount tolerance is 0.01 inclusive across supported currencies; that is a simple project policy, not a provider-specific settlement convention. Synthetic statements demonstrate comparison behavior; they are not automatic imports from Stripe.

## Access and operations

Staff users share the workspace. Token authentication serves API clients; session writes enforce CSRF. Demo setup is restricted to DEBUG and preserves passwords. The demo account has read-only administrative model permissions, while workspace APIs allow the authorized workflow. There are no tenant boundaries or granular payment roles.

Database-backed metrics aggregate state written by worker processes. Process-local counters are still process-local; one API worker simplifies local demonstration, but does not solve distributed histogram aggregation. Grafana is provisioned against the Compose Prometheus datasource.

Production work would require live payment lifecycle design, a ledger, tenant boundaries, role separation, secret rotation, TLS, dependency review, deployment access controls, manual exception handling, migrations/backup drills and high-availability infrastructure. None is implied by a passing sandbox demo.

Primary references: [Stripe webhooks](https://docs.stripe.com/webhooks), [Checkout Sessions](https://docs.stripe.com/api/checkout/sessions/create?lang=python), [dynamic payment methods](https://docs.stripe.com/payments/payment-methods/dynamic-payment-methods), [Stripe Python SDK](https://github.com/stripe/stripe-python).

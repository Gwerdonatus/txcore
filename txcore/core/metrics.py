from prometheus_client import Counter, Histogram, Gauge

# Transaction metrics
TRANSACTIONS_CREATED = Counter(
    "txcore_transactions_created_total",
    "Total number of transactions created",
    ["currency", "status"],
)

TRANSACTION_AMOUNT = Histogram(
    "txcore_transaction_amount",
    "Distribution of transaction amounts",
    ["currency"],
    buckets=[10, 50, 100, 500, 1000, 5000, 10000, 50000],
)

# Webhook metrics
WEBHOOKS_RECEIVED = Counter(
    "txcore_webhooks_received_total",
    "Total webhooks received",
    ["provider", "event_type"],
)

WEBHOOK_VALIDATION_FAILURES = Counter(
    "txcore_webhook_validation_failures_total",
    "Webhook HMAC validation failures",
    ["provider"],
)

# Reconciliation metrics
RECONCILIATION_RUNS = Counter(
    "txcore_reconciliation_runs_total",
    "Total reconciliation jobs run",
    ["status"],
)

RECONCILIATION_DISCREPANCIES = Gauge(
    "txcore_reconciliation_discrepancies",
    "Number of unresolved reconciliation discrepancies",
)

# Worker metrics
CELERY_TASKS_PROCESSED = Counter(
    "txcore_celery_tasks_processed_total",
    "Total Celery tasks processed",
    ["task_name", "status"],
)

CELERY_TASK_DURATION = Histogram(
    "txcore_celery_task_duration_seconds",
    "Celery task execution time",
    ["task_name"],
)

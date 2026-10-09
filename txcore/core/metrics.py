from prometheus_client import Counter, Histogram, Gauge, REGISTRY

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


class DatabaseMetricsCollector:
    """Business-state gauges come from the shared database, including worker writes."""

    def describe(self):
        from prometheus_client.core import GaugeMetricFamily

        yield GaugeMetricFamily("txcore_transaction_state", "Stored transactions by state", labels=["status"])
        yield GaugeMetricFamily("txcore_webhook_state", "Stored webhook reports by state", labels=["status"])
        yield GaugeMetricFamily("txcore_outbox_pending", "Events awaiting Kafka acknowledgement")

    def collect(self):
        from prometheus_client.core import GaugeMetricFamily
        from django.db.models import Count
        from txcore.apps.transactions.models import Transaction, OutboxEvent
        from txcore.apps.webhooks.models import WebhookEvent

        for model, name, description in [
            (Transaction, "txcore_transaction_state", "Stored transactions by state"),
            (WebhookEvent, "txcore_webhook_state", "Stored webhook reports by state"),
        ]:
            metric = GaugeMetricFamily(name, description, labels=["status"])
            counts = dict(
                model.objects.values("status").annotate(count=Count("pk")).values_list("status", "count")
            )
            for state in model.Status.values:
                metric.add_metric([state], counts.get(state, 0))
            yield metric
        pending = GaugeMetricFamily("txcore_outbox_pending", "Events awaiting Kafka acknowledgement")
        pending.add_metric([], OutboxEvent.objects.filter(published_at__isnull=True).count())
        yield pending


REGISTRY.register(DatabaseMetricsCollector())

import uuid
from django.db import models
from django.utils import timezone


class Transaction(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SETTLED = "settled", "Settled"
        FAILED = "failed", "Failed"
        REVERSED = "reversed", "Reversed"

    class Currency(models.TextChoices):
        USD = "USD", "US Dollar"
        EUR = "EUR", "Euro"
        GBP = "GBP", "British Pound"
        NGN = "NGN", "Nigerian Naira"
        JPY = "JPY", "Japanese Yen"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idempotency_key = models.CharField(max_length=255, unique=True, db_index=True)
    reference = models.CharField(max_length=100, unique=True, db_index=True)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.USD)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    request_fingerprint = models.CharField(max_length=64, blank=True)
    checkout_url = models.URLField(max_length=2048, blank=True)

    # Payment provider fields
    provider = models.CharField(max_length=50, blank=True)
    provider_reference = models.CharField(max_length=255, blank=True, db_index=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["provider", "provider_reference"]),
        ]

    def __str__(self):
        return f"Transaction {self.reference} — {self.amount} {self.currency} [{self.status}]"


class OutboxEvent(models.Model):
    """Persist event intent with the business write; relay is at least once."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_key = models.CharField(max_length=255, unique=True)
    topic = models.CharField(max_length=30)
    aggregate_id = models.CharField(max_length=100)
    payload = models.JSONField()
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    available_at = models.DateTimeField(default=timezone.now)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["published_at", "available_at"])]

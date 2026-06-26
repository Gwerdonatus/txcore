import uuid
from django.db import models


class WebhookEvent(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSING = "processing", "Processing"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=50, db_index=True)
    event_type = models.CharField(max_length=100, db_index=True)
    payload = models.JSONField()
    signature = models.CharField(max_length=512, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)

    # Link to transaction if applicable
    transaction_reference = models.CharField(max_length=100, blank=True, db_index=True)

    # Retry tracking
    retry_count = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)

    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["provider", "event_type", "status"]),
        ]

    def __str__(self):
        return f"WebhookEvent {self.provider}/{self.event_type} [{self.status}]"

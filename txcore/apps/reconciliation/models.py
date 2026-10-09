import uuid
from django.db import models


class ReconciliationRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    filename = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    total_rows = models.IntegerField(default=0)
    matched = models.IntegerField(default=0)
    discrepancies = models.IntegerField(default=0)
    skipped = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"ReconciliationRun {self.filename} [{self.status}]"


class ReconciliationDiscrepancy(models.Model):
    class Type(models.TextChoices):
        AMOUNT_MISMATCH = "amount_mismatch", "Amount Mismatch"
        NOT_FOUND = "not_found", "Transaction Not Found"
        STATUS_MISMATCH = "status_mismatch", "Status Mismatch"
        CURRENCY_MISMATCH = "currency_mismatch", "Currency Mismatch"
        DUPLICATE = "duplicate", "Duplicate Entry"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(ReconciliationRun, on_delete=models.CASCADE, related_name="discrepancy_set")
    reference = models.CharField(max_length=100, db_index=True)
    discrepancy_type = models.CharField(max_length=30, choices=Type.choices)
    expected_amount = models.DecimalField(max_digits=19, decimal_places=4, null=True)
    actual_amount = models.DecimalField(max_digits=19, decimal_places=4, null=True)
    expected_currency = models.CharField(max_length=3, blank=True)
    actual_currency = models.CharField(max_length=3, blank=True)
    expected_status = models.CharField(max_length=20, blank=True)
    actual_status = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["run", "discrepancy_type"]),
            models.Index(fields=["reference", "resolved"]),
        ]

    def __str__(self):
        return f"Discrepancy {self.reference} [{self.discrepancy_type}]"

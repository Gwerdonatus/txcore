"""OpenAPI shapes for the existing dictionary-based API responses."""
from rest_framework import serializers
from txcore.apps.transactions.serializers import TransactionResponseSerializer


class TransactionListResponse(serializers.Serializer):
    count = serializers.IntegerField()
    results = TransactionResponseSerializer(many=True)


class WebhookPayload(serializers.Serializer):
    event_type = serializers.CharField()
    reference = serializers.CharField(required=False)
    data = serializers.JSONField(required=False)


class WebhookAccepted(serializers.Serializer):
    received = serializers.BooleanField()
    event_id = serializers.UUIDField()


class WebhookRecord(serializers.Serializer):
    id = serializers.UUIDField()
    provider = serializers.CharField()
    event_type = serializers.CharField()
    status = serializers.CharField()
    transaction_reference = serializers.CharField()
    retry_count = serializers.IntegerField()
    received_at = serializers.DateTimeField()


class WebhookListResponse(serializers.Serializer):
    count = serializers.IntegerField()
    results = WebhookRecord(many=True)


class ReconciliationUpload(serializers.Serializer):
    file = serializers.FileField()


class ReconciliationSummary(serializers.Serializer):
    run_id = serializers.UUIDField()
    status = serializers.CharField()
    filename = serializers.CharField()
    total_rows = serializers.IntegerField()
    matched = serializers.IntegerField()
    discrepancies = serializers.IntegerField()
    skipped = serializers.IntegerField(required=False)
    error_message = serializers.CharField(allow_null=True, required=False)
    created_at = serializers.DateTimeField(required=False)


class DiscrepancyDetail(serializers.Serializer):
    reference = serializers.CharField()
    type = serializers.CharField()
    expected_amount = serializers.CharField(allow_null=True)
    actual_amount = serializers.CharField(allow_null=True)
    expected_status = serializers.CharField()
    actual_status = serializers.CharField()
    notes = serializers.CharField()
    resolved = serializers.BooleanField()


class ReconciliationDetail(ReconciliationSummary):
    discrepancy_detail = DiscrepancyDetail(many=True)


class ReconciliationListResponse(serializers.Serializer):
    count = serializers.IntegerField()
    results = ReconciliationSummary(many=True)

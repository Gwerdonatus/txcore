import json
import logging
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from txcore.core.metrics import WEBHOOKS_RECEIVED, WEBHOOK_VALIDATION_FAILURES
from txcore.events.kafka_producer import publish
from .models import WebhookEvent
from .signature import validate_signature

logger = logging.getLogger(__name__)


class WebhookIngestView(APIView):
    """
    POST /api/v1/webhooks/ingest/<provider>/
    Validates HMAC signature and stores the event for async processing.
    """

    @extend_schema(
        responses={202: {"description": "Webhook accepted for processing"}},
    )
    def post(self, request, provider):
        raw_body = request.body
        signature = request.headers.get("X-Webhook-Signature", "")

        # Validate HMAC — reject unsigned events
        if not validate_signature(raw_body, signature, provider):
            WEBHOOK_VALIDATION_FAILURES.labels(provider=provider).inc()
            return Response(
                {"error": {"detail": "Invalid webhook signature."}},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            return Response(
                {"error": {"detail": "Invalid JSON payload."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        event_type = payload.get("event_type") or payload.get("type", "unknown")
        transaction_ref = (
            payload.get("data", {}).get("reference")
            or payload.get("reference", "")
        )

        event = WebhookEvent.objects.create(
            provider=provider,
            event_type=event_type,
            payload=payload,
            signature=signature,
            transaction_reference=transaction_ref,
            status=WebhookEvent.Status.RECEIVED,
        )

        WEBHOOKS_RECEIVED.labels(provider=provider, event_type=event_type).inc()

        # Publish to Kafka for async workers
        publish(
            "webhooks",
            key=str(event.id),
            payload={
                "event": "webhook_received",
                "webhook_id": str(event.id),
                "provider": provider,
                "event_type": event_type,
                "transaction_reference": transaction_ref,
            },
        )

        logger.info("Webhook accepted: provider=%s event_type=%s id=%s", provider, event_type, event.id)
        return Response(
            {"received": True, "event_id": str(event.id)},
            status=status.HTTP_202_ACCEPTED,
        )


class WebhookEventListView(APIView):
    """GET /api/v1/webhooks/?provider=stripe&status=received"""

    def get(self, request):
        queryset = WebhookEvent.objects.all()

        provider = request.query_params.get("provider")
        event_status = request.query_params.get("status")
        event_type = request.query_params.get("event_type")

        if provider:
            queryset = queryset.filter(provider=provider)
        if event_status:
            queryset = queryset.filter(status=event_status)
        if event_type:
            queryset = queryset.filter(event_type=event_type)

        queryset = queryset[:50]

        data = [
            {
                "id": str(e.id),
                "provider": e.provider,
                "event_type": e.event_type,
                "status": e.status,
                "transaction_reference": e.transaction_reference,
                "retry_count": e.retry_count,
                "received_at": e.received_at.isoformat(),
            }
            for e in queryset
        ]
        return Response({"count": len(data), "results": data})

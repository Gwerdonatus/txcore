import json
import logging
import hashlib
import stripe
from django.conf import settings
from django.db import transaction
from rest_framework.permissions import AllowAny
from txcore.providers.stripe import verify_event, SandboxNotConfigured
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter

from txcore.core.schema import WebhookPayload, WebhookAccepted, WebhookListResponse
from txcore.core.metrics import WEBHOOKS_RECEIVED, WEBHOOK_VALIDATION_FAILURES
from txcore.events.outbox import enqueue
from .models import WebhookEvent
from .signature import validate_signature

logger = logging.getLogger(__name__)


class WebhookIngestView(APIView):
    """
    POST /api/v1/webhooks/ingest/<provider>/
    Validates HMAC signature and stores the event for async processing.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=["Webhooks"],
        request=WebhookPayload,
        responses={202: WebhookAccepted},
        parameters=[
            OpenApiParameter(
                name="Stripe-Signature",
                location=OpenApiParameter.HEADER,
                description="Required for stripe: timestamped Stripe signature over exact request bytes.",
            ),
            OpenApiParameter(
                name="X-Webhook-Signature",
                location=OpenApiParameter.HEADER,
                required=False,
                description="For demo only: generic HMAC-SHA256 of the exact request bytes.",
            ),
        ],
    )
    def post(self, request, provider):
        raw_body = request.body
        signature = request.headers.get("X-Webhook-Signature", "")

        if len(raw_body) > 256 * 1024:
            return Response({"error": "Webhook body too large."}, status=413)
        if provider == "stripe":
            try:
                payload = verify_event(raw_body, request.headers.get("Stripe-Signature", ""))
                payload = payload.to_dict()
                if payload.get("livemode") is not False or not payload.get("id"):
                    return Response({"error": "Only identified sandbox events are accepted."}, status=400)
            except SandboxNotConfigured as exc:
                return Response({"error": str(exc)}, status=503)
            except stripe.SignatureVerificationError as exc:
                category = "timestamp" if "Timestamp" in str(exc) else "signature"
                logger.warning("Stripe webhook rejected: %s verification failed", category)
                return Response({"error": "Invalid Stripe signature or timestamp."}, status=400)
            except ValueError:
                logger.warning("Stripe webhook rejected: invalid event JSON")
                return Response({"error": "Invalid Stripe event JSON."}, status=400)
        elif provider == "demo" and settings.DEBUG:
            if not validate_signature(raw_body, signature, provider):
                WEBHOOK_VALIDATION_FAILURES.labels(provider=provider).inc()
                return Response({"error": "Invalid demo signature."}, status=401)
            try:
                payload = json.loads(raw_body)
            except (ValueError, UnicodeDecodeError):
                return Response({"error": "Invalid JSON payload."}, status=400)
        else:
            return Response({"error": "Provider is not supported."}, status=404)
        if not isinstance(payload, dict) or not isinstance(payload.get("data", {}), dict):
            return Response({"error": "Event must be a JSON object with object data."}, status=400)
        event_type = payload.get("event_type") or payload.get("type", "unknown")
        transaction_ref = payload.get("data", {}).get("reference") or payload.get("reference", "")

        event_id = payload.get("id") if provider == "stripe" else hashlib.sha256(raw_body).hexdigest()
        if not isinstance(event_type, str) or len(event_type) > 100 or len(str(event_id)) > 255:
            return Response({"error": "Invalid event identifier or type."}, status=400)
        with transaction.atomic():
            event, created = WebhookEvent.objects.get_or_create(
                provider=provider,
                provider_event_id=event_id,
                defaults={
                    "event_type": event_type,
                    "payload": payload,
                    "transaction_reference": str(transaction_ref)[:100],
                    "status": WebhookEvent.Status.RECEIVED,
                },
            )
            if not created and event.payload != payload:
                return Response({"error": "Event identifier conflicts with stored payload."}, status=409)
            if created:
                enqueue(
                    "webhooks",
                    event.id,
                    "webhook_received",
                    {
                        "webhook_id": str(event.id),
                        "provider": provider,
                        "event_type": event_type,
                    },
                )
                WEBHOOKS_RECEIVED.labels(provider=provider, event_type=event_type).inc()

        logger.info("Webhook accepted: provider=%s event_type=%s id=%s", provider, event_type, event.id)
        return Response(
            {"received": True, "event_id": str(event.id)},
            status=status.HTTP_202_ACCEPTED,
        )


class WebhookEventListView(APIView):
    """GET /api/v1/webhooks/?provider=stripe&status=received"""

    @extend_schema(tags=["Webhooks"], responses={200: WebhookListResponse})
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

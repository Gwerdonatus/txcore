import logging
import uuid
import hashlib
import json
from django.db import transaction as db_transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter

from txcore.core.schema import TransactionListResponse
from txcore.core.metrics import TRANSACTIONS_CREATED, TRANSACTION_AMOUNT
from txcore.events.outbox import enqueue
from .models import Transaction
from .serializers import TransactionCreateSerializer, TransactionResponseSerializer

logger = logging.getLogger(__name__)


class TransactionCreateView(APIView):
    """
    POST /api/v1/transactions/create/
    Creates a payment transaction with idempotency guarantees.
    Requires Idempotency-Key header.
    """

    @extend_schema(
        tags=["Transactions"],
        operation_id="create_transaction",
        request=TransactionCreateSerializer,
        responses={201: TransactionResponseSerializer, 200: TransactionResponseSerializer},
        parameters=[
            OpenApiParameter(
                name="Idempotency-Key",
                location=OpenApiParameter.HEADER,
                required=True,
                description="Unique key to prevent duplicate transactions",
            )
        ],
    )
    def post(self, request):
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return Response(
                {"error": {"detail": "Idempotency-Key header is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TransactionCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": {"detail": serializer.errors}},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        if len(idempotency_key) > 128:
            return Response(
                {"error": {"detail": "Idempotency-Key must be at most 128 characters."}}, status=400
            )
        data = serializer.validated_data
        canonical = {
            **data,
            "amount": str(data["amount"].normalize()),
            "currency": data.get("currency", "USD"),
            "description": data.get("description", ""),
            "provider": data.get("provider", "demo"),
            "metadata": data.get("metadata", {}),
        }
        fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
        scoped_key = hashlib.sha256(f"{request.user.pk}:{idempotency_key}".encode()).hexdigest()
        reference = f"TXN-{uuid.uuid4().hex[:12].upper()}"

        with db_transaction.atomic():
            transaction, created = Transaction.objects.get_or_create(
                idempotency_key=scoped_key,
                defaults={
                    "reference": reference,
                    "amount": data["amount"],
                    "currency": canonical["currency"],
                    "description": canonical["description"],
                    "metadata": canonical["metadata"],
                    "provider": canonical["provider"],
                    "request_fingerprint": fingerprint,
                    "status": Transaction.Status.PENDING,
                },
            )
            if not created:
                if transaction.request_fingerprint != fingerprint:
                    return Response(
                        {"error": {"detail": "Idempotency-Key was used with another request body."}},
                        status=409,
                    )
                return Response(TransactionResponseSerializer(transaction).data, status=200)
            enqueue(
                "transactions",
                transaction.id,
                "payment_created",
                {
                    "transaction_id": str(transaction.id),
                    "reference": transaction.reference,
                    "amount": str(transaction.amount),
                    "currency": transaction.currency,
                    "status": transaction.status,
                },
            )

        # Prometheus metrics
        TRANSACTIONS_CREATED.labels(
            currency=transaction.currency,
            status=transaction.status,
        ).inc()
        TRANSACTION_AMOUNT.labels(currency=transaction.currency).observe(float(transaction.amount))

        response_data = TransactionResponseSerializer(transaction).data

        logger.info("Transaction created: %s", transaction.reference)
        return Response(response_data, status=status.HTTP_201_CREATED)


class TransactionDetailView(APIView):
    """GET /api/v1/transactions/<reference>/"""

    @extend_schema(
        tags=["Transactions"],
        operation_id="get_transaction",
        responses={200: TransactionResponseSerializer},
    )
    def get(self, request, reference):
        try:
            transaction = Transaction.objects.get(reference=reference)
        except Transaction.DoesNotExist:
            return Response(
                {"error": {"detail": "Transaction not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = TransactionResponseSerializer(transaction)
        return Response(serializer.data)


class TransactionListView(APIView):
    """GET /api/v1/transactions/?status=pending&currency=USD"""

    @extend_schema(
        tags=["Transactions"],
        operation_id="list_transactions",
        responses={200: TransactionListResponse},
    )
    def get(self, request):
        queryset = Transaction.objects.all().select_related()

        tx_status = request.query_params.get("status")
        currency = request.query_params.get("currency")

        if tx_status:
            queryset = queryset.filter(status=tx_status)
        if currency:
            queryset = queryset.filter(currency=currency.upper())

        # Limit to 100 for safety
        queryset = queryset[:100]
        serializer = TransactionResponseSerializer(queryset, many=True)
        return Response({"count": len(serializer.data), "results": serializer.data})

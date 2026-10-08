import logging
import uuid
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter

from txcore.core.idempotency import get_cached_response, cache_response
from txcore.core.schema import TransactionListResponse
from txcore.core.metrics import TRANSACTIONS_CREATED, TRANSACTION_AMOUNT
from txcore.events.kafka_producer import publish
from .models import Transaction
from .serializers import TransactionCreateSerializer, TransactionResponseSerializer

logger = logging.getLogger(__name__)


class TransactionCreateView(APIView):
    """
    POST /api/v1/transactions/
    Creates a payment transaction with idempotency guarantees.
    Requires Idempotency-Key header.
    """

    @extend_schema(
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

        # Check idempotency cache — return early if seen before
        cached = get_cached_response(idempotency_key)
        if cached:
            logger.info("Idempotent replay for key: %s", idempotency_key)
            return Response(cached, status=status.HTTP_200_OK)

        serializer = TransactionCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": {"detail": serializer.errors}},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        data = serializer.validated_data
        reference = f"TXN-{uuid.uuid4().hex[:12].upper()}"

        transaction, created = Transaction.objects.get_or_create(
            idempotency_key=idempotency_key,
            defaults={
                "reference": reference,
                "amount": data["amount"],
                "currency": data.get("currency", Transaction.Currency.USD),
                "description": data.get("description", ""),
                "metadata": data.get("metadata", {}),
                "provider": data.get("provider", ""),
                "status": Transaction.Status.PENDING,
            },
        )
        if not created:
            return Response(TransactionResponseSerializer(transaction).data, status=status.HTTP_200_OK)

        # Prometheus metrics
        TRANSACTIONS_CREATED.labels(
            currency=transaction.currency,
            status=transaction.status,
        ).inc()
        TRANSACTION_AMOUNT.labels(currency=transaction.currency).observe(
            float(transaction.amount)
        )

        # Publish event to Kafka
        publish(
            "transactions",
            key=str(transaction.id),
            payload={
                "event": "payment_created",
                "transaction_id": str(transaction.id),
                "reference": transaction.reference,
                "amount": str(transaction.amount),
                "currency": transaction.currency,
                "status": transaction.status,
            },
        )

        response_data = TransactionResponseSerializer(transaction).data
        # Store as plain dict for JSON serialisation in cache
        response_dict = dict(response_data)
        response_dict["id"] = str(response_dict["id"])
        response_dict["created_at"] = str(response_dict["created_at"])
        response_dict["updated_at"] = str(response_dict["updated_at"])

        cache_response(idempotency_key, response_dict)

        logger.info("Transaction created: %s", transaction.reference)
        return Response(response_data, status=status.HTTP_201_CREATED)


class TransactionDetailView(APIView):
    """GET /api/v1/transactions/<reference>/"""

    @extend_schema(responses={200: TransactionResponseSerializer})
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

    @extend_schema(responses={200: TransactionListResponse})
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

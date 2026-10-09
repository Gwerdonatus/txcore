import stripe
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from txcore.providers.stripe import create_checkout, SandboxNotConfigured
from .models import Transaction


class CheckoutResponse(serializers.Serializer):
    reference = serializers.CharField()
    checkout_url = serializers.URLField()
    sandbox = serializers.BooleanField()


class CheckoutView(APIView):
    @extend_schema(tags=["Stripe sandbox"], request=None, responses={200: CheckoutResponse})
    def post(self, request, reference):
        # Serialize concurrent sessions for one transaction; Stripe's stable key
        # recovers the same external session if the process dies before commit.
        try:
            with transaction.atomic():
                tx = Transaction.objects.select_for_update().get(reference=reference)
                if tx.provider != "stripe":
                    return Response(
                        {"error": "This transaction is not a Stripe sandbox payment."}, status=400
                    )
                if tx.status not in {"pending", "processing"}:
                    return Response({"error": "Transaction is already terminal."}, status=409)
                if not tx.checkout_url:
                    session = create_checkout(tx)
                    if session.livemode or not session.id.startswith("cs_test_"):
                        raise SandboxNotConfigured("Live Checkout sessions are disabled.")
                    tx.checkout_url = session.url
                    tx.provider_reference = session.id
                    tx.status = Transaction.Status.PROCESSING
                    tx.save(update_fields=["checkout_url", "provider_reference", "status", "updated_at"])
                return Response({"reference": tx.reference, "checkout_url": tx.checkout_url, "sandbox": True})
        except Transaction.DoesNotExist:
            return Response({"error": "Transaction not found."}, status=404)
        except SandboxNotConfigured as exc:
            return Response({"error": str(exc)}, status=503)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=422)
        except stripe.StripeError:
            return Response(
                {"error": "Stripe could not initialize checkout. Retry with the same transaction."},
                status=502,
            )

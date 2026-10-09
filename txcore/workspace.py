from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from txcore.apps.transactions.models import Transaction, OutboxEvent
from txcore.apps.webhooks.models import WebhookEvent
from txcore.apps.reconciliation.models import ReconciliationRun


@staff_member_required(login_url="/login/")
def workspace(request):
    return render(
        request,
        "txcore/workspace.html",
        {
            "transactions": Transaction.objects.all()[:20],
            "webhooks": WebhookEvent.objects.all()[:10],
            "runs": ReconciliationRun.objects.all()[:10],
            "transaction_count": Transaction.objects.count(),
            "settled_count": Transaction.objects.filter(status="settled").count(),
            "pending_events": OutboxEvent.objects.filter(published_at__isnull=True).count(),
            "failed_webhooks": WebhookEvent.objects.filter(status="failed").count(),
            "stripe_configured": settings.STRIPE_SECRET_KEY.startswith("sk_test_"),
            "webhook_configured": settings.STRIPE_WEBHOOK_SECRET.startswith("whsec_"),
            "cancelled": request.GET.get("cancelled") == "1",
            "returned": bool(request.GET.get("session_id")),
            "return_payment": Transaction.objects.filter(
                provider="stripe",
                provider_reference=request.GET.get("session_id", ""),
            )
            .exclude(provider_reference="")
            .first(),
        },
    )

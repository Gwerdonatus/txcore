"""Retry acknowledged Kafka delivery without losing business events."""

from datetime import timedelta
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from txcore.apps.transactions.models import OutboxEvent
from txcore.events.kafka_producer import publish


@shared_task(name="workers.deliver_outbox")
def deliver_outbox():
    delivered = 0
    ids = list(
        OutboxEvent.objects.filter(
            published_at__isnull=True,
            available_at__lte=timezone.now(),
        ).values_list(
            "id", flat=True
        )[:100]
    )
    for event_id in ids:
        with transaction.atomic():
            event = OutboxEvent.objects.select_for_update().get(id=event_id)
            if event.published_at or event.available_at > timezone.now():
                continue
            event.attempts += 1
            try:
                acknowledged = publish(
                    event.topic, event.aggregate_id, {**event.payload, "event_id": str(event.id)}
                )
            except Exception:
                acknowledged = False
            if acknowledged:
                event.published_at = timezone.now()
                event.last_error = ""
                delivered += 1
            else:
                event.last_error = "Kafka publication was not acknowledged; retained for retry."
                event.available_at = timezone.now() + timedelta(seconds=min(300, 2 ** min(event.attempts, 8)))
            event.save()
    return {"delivered": delivered}

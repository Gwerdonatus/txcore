from txcore.apps.transactions.models import OutboxEvent


def enqueue(topic, aggregate_id, event, payload):
    return OutboxEvent.objects.get_or_create(
        event_key=f"{topic}:{aggregate_id}:{event}",
        defaults={"topic": topic, "aggregate_id": str(aggregate_id), "payload": {**payload, "event": event}},
    )[0]

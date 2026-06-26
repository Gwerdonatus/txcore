import json
import logging
from datetime import datetime, timezone
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_producer():
    """Lazy import so the app works without Kafka running (tests, local dev)."""
    try:
        from kafka import KafkaProducer
        return KafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks="all",
            retries=3,
            max_block_ms=5000,
        )
    except Exception as exc:
        logger.warning("Kafka producer unavailable: %s — events will be skipped", exc)
        return None


_producer = None


def _producer_instance():
    global _producer
    if _producer is None:
        _producer = _get_producer()
    return _producer


def publish(topic_key: str, key: str, payload: dict) -> bool:
    """
    Publish a message to a Kafka topic.
    Returns True on success, False if Kafka is unavailable.
    topic_key maps to settings.KAFKA_TOPICS.
    """
    producer = _producer_instance()
    if producer is None:
        logger.warning("Skipping Kafka publish — producer not available")
        return False

    topic = settings.KAFKA_TOPICS.get(topic_key)
    if not topic:
        logger.error("Unknown Kafka topic key: %s", topic_key)
        return False

    payload["_published_at"] = datetime.now(timezone.utc).isoformat()

    try:
        future = producer.send(topic, key=key, value=payload)
        future.get(timeout=5)
        logger.debug("Published to %s key=%s", topic, key)
        return True
    except Exception as exc:
        logger.error("Failed to publish to Kafka topic %s: %s", topic, exc)
        return False

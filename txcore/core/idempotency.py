import hashlib
import json
import logging
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)

TTL = getattr(settings, "IDEMPOTENCY_KEY_TTL", 86400)


def _cache_key(idempotency_key: str) -> str:
    hashed = hashlib.sha256(idempotency_key.encode()).hexdigest()
    return f"idempotency:{hashed}"


def get_cached_response(idempotency_key: str) -> dict | None:
    """Return the previously cached response for this key, or None."""
    key = _cache_key(idempotency_key)
    cached = cache.get(key)
    if cached:
        logger.debug("Idempotency cache hit for key: %s", idempotency_key)
        return json.loads(cached)
    return None


def cache_response(idempotency_key: str, response_data: dict) -> None:
    """Store a response under the given idempotency key for TTL seconds."""
    key = _cache_key(idempotency_key)
    cache.set(key, json.dumps(response_data), timeout=TTL)
    logger.debug("Cached response for idempotency key: %s", idempotency_key)


def delete_cached_response(idempotency_key: str) -> None:
    """Remove a cached response — used in tests."""
    key = _cache_key(idempotency_key)
    cache.delete(key)

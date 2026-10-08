import hashlib
import hmac
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def validate_signature(payload_bytes: bytes, signature: str, provider: str = "default") -> bool:
    """
    Validate HMAC-SHA256 webhook signature.
    Supports a generic 'sha256=<hex>' prefix or raw hex signatures.
    This is not a provider-specific timestamped signing protocol.
    """
    secret = settings.WEBHOOK_SECRET.encode("utf-8")
    expected = hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest()

    # Strip provider prefixes e.g. "sha256=abc123"
    received = signature.split("=")[-1] if "=" in signature else signature

    is_valid = hmac.compare_digest(expected, received)
    if not is_valid:
        logger.warning("Webhook signature mismatch for provider: %s", provider)
    return is_valid


def compute_signature(payload_bytes: bytes) -> str:
    """Generate a valid HMAC-SHA256 signature for test/dev use."""
    secret = settings.WEBHOOK_SECRET.encode("utf-8")
    return hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest()

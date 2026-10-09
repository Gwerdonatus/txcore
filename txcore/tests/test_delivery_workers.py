"""Regression checks for producer acknowledgement and simulated worker behavior."""
import json
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone

from txcore.apps.transactions.models import Transaction
from txcore.events import kafka_producer
from txcore.workers.alerts import check_sla_breaches
from txcore.workers.settlement import process_settlement


def test_publish_requires_acknowledgement_and_adds_timestamp():
    producer = Mock()
    with patch.object(kafka_producer, "_producer_instance", return_value=producer):
        payload = {"event": "test"}
        assert kafka_producer.publish("transactions", "key", payload)
    producer.send.assert_called_once_with("txcore.transactions", key="key", value=payload)
    producer.send.return_value.get.assert_called_once_with(timeout=5)
    assert "_published_at" in payload


@pytest.mark.parametrize("failure", ["missing", "acknowledgement", "unknown_topic"])
def test_publish_reports_delivery_failures(failure):
    producer = Mock()
    if failure == "acknowledgement":
        producer.send.return_value.get.side_effect = TimeoutError("broker acknowledgement timed out")
    instance = None if failure == "missing" else producer
    with patch.object(kafka_producer, "_producer_instance", return_value=instance):
        topic = "unknown" if failure == "unknown_topic" else "transactions"
        assert not kafka_producer.publish(topic, "key", {"event": "test"})
    if failure != "acknowledgement":
        producer.send.assert_not_called()


def test_producer_configuration_serializes_keys_and_payloads():
    constructor = Mock()
    with patch.dict("sys.modules", {"kafka": SimpleNamespace(KafkaProducer=constructor)}):
        assert kafka_producer._get_producer() == constructor.return_value
    config = constructor.call_args.kwargs
    assert config["acks"] == "all"
    assert config["retries"] == 3
    assert json.loads(config["value_serializer"]({"x": 1})) == {"x": 1}
    assert config["key_serializer"]("key") == b"key"
    assert config["key_serializer"](None) is None


def test_producer_initialization_failure_is_reported():
    constructor = Mock(side_effect=ConnectionError("broker unavailable"))
    with patch.dict("sys.modules", {"kafka": SimpleNamespace(KafkaProducer=constructor)}):
        assert kafka_producer._get_producer() is None


def test_producer_instance_is_reused():
    with (
        patch.object(kafka_producer, "_producer", None),
        patch.object(kafka_producer, "_get_producer") as create,
    ):
        assert kafka_producer._producer_instance() == create.return_value
        assert kafka_producer._producer_instance() == create.return_value
        create.assert_called_once()


def make_transaction(status="pending"):
    return Transaction.objects.create(
        reference=f"TXN-{uuid.uuid4().hex}", idempotency_key=uuid.uuid4().hex,
        amount="42.00", currency="EUR", provider="demo", status=status,
    )


def test_settlement_persists_completion_and_skips_repeat():
    transaction = make_transaction()
    with patch("txcore.workers.settlement.publish", return_value=True) as publish:
        process_settlement.run(str(transaction.id))
        process_settlement.run(str(transaction.id))
    transaction.refresh_from_db()
    assert transaction.status == Transaction.Status.SETTLED
    assert transaction.settled_at is not None
    publish.assert_called_once()
    assert publish.call_args.kwargs["payload"]["reference"] == transaction.reference


def test_missing_settlement_transaction_does_not_publish():
    with patch("txcore.workers.settlement.publish") as publish:
        process_settlement.run(str(uuid.uuid4()))
    publish.assert_not_called()


def test_settlement_exception_requests_retry():
    transaction = make_transaction()
    retry_error = RuntimeError("retry requested")
    with patch("txcore.workers.settlement.publish", side_effect=ConnectionError("publication failed")), \
            patch.object(process_settlement, "retry", side_effect=retry_error) as retry:
        with pytest.raises(RuntimeError, match="retry requested"):
            process_settlement.run(str(transaction.id))
    retry.assert_called_once()
    assert retry.call_args.kwargs["countdown"] == 60


def test_sla_checks_only_old_unsettled_transactions():
    old = make_transaction()
    settled = make_transaction("settled")
    make_transaction()
    Transaction.objects.filter(id__in=[old.id, settled.id]).update(
        created_at=timezone.now() - timedelta(minutes=45),
    )
    with patch("txcore.workers.alerts.publish", return_value=True) as publish:
        assert check_sla_breaches.run() == {"breaching_count": 1}
    publish.assert_called_once()
    payload = publish.call_args.kwargs["payload"]
    assert payload["reference"] == old.reference
    assert payload["age_minutes"] >= 45


def test_sla_check_without_breach_does_not_publish():
    make_transaction()
    with patch("txcore.workers.alerts.publish") as publish:
        assert check_sla_breaches.run() == {"breaching_count": 0}
    publish.assert_not_called()

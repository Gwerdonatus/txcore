#!/bin/bash
# TxCore API smoke tests
# Run after docker-compose up: bash scripts/test_api.sh

BASE_URL="${BASE_URL:-http://localhost:8100}"
WEBHOOK_SECRET="local-webhook-secret"

echo ""
echo "========================================"
echo "  TxCore API Smoke Tests"
echo "========================================"

# 1. Create a transaction
echo ""
echo "1. Creating a transaction..."
IDEM_KEY="smoke-test-$(date +%s)"
RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/transactions/create/" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $IDEM_KEY" \
  -d '{"amount": "250.00", "currency": "USD", "description": "Smoke test payment", "provider": "stripe"}')
echo "$RESPONSE" | python3 -m json.tool
REFERENCE=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('reference',''))")

# 2. Test idempotency — same key should return 200
echo ""
echo "2. Testing idempotency (same key — expect HTTP 200)..."
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" -X POST "$BASE_URL/api/v1/transactions/create/" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $IDEM_KEY" \
  -d '{"amount": "250.00", "currency": "USD"}'

# 3. Get transaction by reference
echo ""
echo "3. Fetching transaction: $REFERENCE"
curl -s "$BASE_URL/api/v1/transactions/$REFERENCE/" | python3 -m json.tool

# 4. List transactions
echo ""
echo "4. Listing transactions (status=pending)..."
curl -s "$BASE_URL/api/v1/transactions/?status=pending" | python3 -m json.tool

# 5. Ingest a webhook with valid signature
echo ""
echo "5. Sending webhook with valid signature..."
PAYLOAD='{"event_type":"payment.success","reference":"TXN-SMOKETEST","data":{"amount":"250.00"}}'
SIGNATURE=$(echo -n "$PAYLOAD" | python3 -c "
import sys, hmac, hashlib
payload = sys.stdin.buffer.read()
sig = hmac.new(b'local-webhook-secret', payload, hashlib.sha256).hexdigest()
print(sig)
")
curl -s -X POST "$BASE_URL/api/v1/webhooks/ingest/stripe/" \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Signature: $SIGNATURE" \
  -d "$PAYLOAD" | python3 -m json.tool

# 6. Webhook with invalid signature — expect 401
echo ""
echo "6. Webhook with invalid signature (expect 401)..."
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" \
  -X POST "$BASE_URL/api/v1/webhooks/ingest/stripe/" \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Signature: invalidsignature" \
  -d "$PAYLOAD"

# 7. Check Prometheus metrics
echo ""
echo "7. Prometheus metrics (txcore_ prefix)..."
curl -s "$BASE_URL/metrics" | grep "^txcore_" | head -20

echo ""
echo "========================================"
echo "  Smoke tests complete"
echo "========================================"

"""Exercise the local prototype with synthetic data; no provider calls or payments."""
import argparse
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


AUTH_TOKEN = ""

def request(base, path, payload=None, headers=None, expected=(200,)):
    data = json.dumps(payload).encode() if payload is not None else None
    request_headers = dict(headers or {})
    if AUTH_TOKEN:
        request_headers["Authorization"] = "Token " + AUTH_TOKEN
    req = urllib.request.Request(base + path, data=data, headers=request_headers)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        response = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as exc:
        response = exc
    status = response.code
    body = json.loads(response.read())
    if status not in expected:
        raise RuntimeError(f"{path}: expected {expected}, received {status}: {body}")
    return status, body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8100")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    if urllib.parse.urlparse(base).hostname not in {"localhost", "127.0.0.1"}:
        parser.error("This synthetic demonstration is restricted to localhost.")
    global AUTH_TOKEN
    _, account = request(base, "/api/token/", {
        "username": "demo.admin", "password": os.environ.get("TXCORE_DEMO_PASSWORD", "TxCoreSandbox123!"),
    })
    AUTH_TOKEN = account["token"]
    transactions = []
    creation_statuses = []
    for index, amount in enumerate(("250.00", "120.00", "80.00"), 1):
        payload = {
            "amount": amount, "currency": "USD", "provider": "demo",
            "description": f"Synthetic demo order {index}; no funds moved",
            "metadata": {"demo_data": True, "external_actions_performed": False},
        }
        headers = {"Idempotency-Key": f"txcore-recruiter-demo-v2-{index}"}
        status, transaction = request(base, "/api/v1/transactions/create/", payload, headers, (200, 201))
        replay_status, replay = request(base, "/api/v1/transactions/create/", payload, headers)
        assert replay["id"] == transaction["id"]
        transactions.append(transaction)
        creation_statuses.append({"create": status, "retry": replay_status})

    reference = transactions[0]["reference"]
    payload = {"event_type": "demo.payment.success", "reference": reference,
               "data": {"demo_data": True, "external_actions_performed": False}}
    secret = os.environ.get("WEBHOOK_SECRET", "local-webhook-secret")
    signature = hmac.new(secret.encode(), json.dumps(payload).encode(), hashlib.sha256).hexdigest()
    valid_status, accepted = request(base, "/api/v1/webhooks/ingest/demo/", payload,
                                    {"X-Webhook-Signature": signature}, (202,))
    invalid_status, rejected = request(base, "/api/v1/webhooks/ingest/demo/", payload,
                                      {"X-Webhook-Signature": "invalid"}, (401,))

    # Local simulation stays pending; it does not simulate a Stripe provider payment.
    csv = "reference,amount,currency,status\n" + "\n".join([
        f"{transactions[0]['reference']},250.00,USD,pending",  # match
        f"{transactions[1]['reference']},119.00,USD,pending",  # amount mismatch
        f"{transactions[2]['reference']},80.00,USD,settled",  # status mismatch
        "TXN-SYNTHETIC-MISSING,50.00,USD,pending",  # absent transaction
    ]) + "\n"
    boundary = "txcore-synthetic-demo-upload"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            "filename=\"synthetic_demo_statement.csv\"\r\nContent-Type: text/csv\r\n\r\n"
            f"{csv}\r\n--{boundary}--\r\n").encode()
    req = urllib.request.Request(base + "/api/v1/reconciliation/upload/", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                                          "Authorization": "Token " + AUTH_TOKEN})
    with urllib.request.urlopen(req, timeout=30) as response:
        assert response.status == 201
        run = json.loads(response.read())
    assert (run["matched"], run["discrepancies"], run["skipped"]) == (1, 3, 0)
    _, detail = request(base, f"/api/v1/reconciliation/{run['run_id']}/")
    assert {d["type"] for d in detail["discrepancy_detail"]} == {
        "amount_mismatch", "status_mismatch", "not_found",
    }
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        _, webhooks = request(base, "/api/v1/webhooks/?provider=demo")
        if any(e["id"] == accepted["event_id"] and e["status"] == "processed" for e in webhooks["results"]):
            break
        time.sleep(1)
    else:
        raise RuntimeError("Beat/worker did not process the accepted webhook.")
    print(json.dumps({"synthetic": True, "external_actions_performed": False,
                      "transaction_reference": reference, "transaction_retries": creation_statuses,
                      "valid_webhook_http": valid_status, "invalid_webhook_http": invalid_status,
                      "reconciliation": run, "reconciliation_detail_url":
                      base + f"/api/v1/reconciliation/{run['run_id']}/"}, indent=2))


if __name__ == "__main__":
    main()

"""Create/reuse an actual sandbox Checkout session; never enters card data."""
import json
import os
import scripts.demo as demo


def main():
    base = "http://localhost:8100"
    _, auth = demo.request(base, "/api/token/", {
        "username": "demo.admin", "password": os.environ.get("TXCORE_DEMO_PASSWORD", "TxCoreSandbox123!"),
    })
    demo.AUTH_TOKEN = auth["token"]
    payload = {"amount": "5.00", "currency": "USD", "provider": "stripe",
               "description": "TxCore Stripe sandbox verification", "metadata": {"sandbox": True}}
    headers = {"Idempotency-Key": "txcore-stripe-verification-v1"}
    _, payment = demo.request(base, "/api/v1/transactions/create/", payload, headers, (200, 201))
    _, replay = demo.request(base, "/api/v1/transactions/create/", payload, headers)
    assert payment["id"] == replay["id"]
    if payment["status"] == "settled":
        print(json.dumps({"reference": payment["reference"], "status": "settled", "sandbox": True}))
        return
    _, checkout = demo.request(base, f"/api/v1/transactions/{payment['reference']}/checkout/", {})
    _, checkout_replay = demo.request(base, f"/api/v1/transactions/{payment['reference']}/checkout/", {})
    assert checkout == checkout_replay
    assert checkout["sandbox"] is True
    print(json.dumps({"reference": payment["reference"], "sandbox": True,
                      "checkout_created": True, "checkout_retry_same_session": True,
                      "next_step": "Complete this transaction in the authenticated browser workspace."}, indent=2))


if __name__ == "__main__":
    main()

# Screenshot provenance

Captured from the actual running TxCore application on **9 October 2026**. Images show its authenticated Django workspace, DRF browsable API, OpenAPI, Stripe-hosted **Sandbox** Checkout, Prometheus and Grafana. No UI, status or metric was generated for these pictures.

Stripe Checkout uses public test card details and a synthetic buyer. Local simulations are separate and explicitly labelled. `settled` on a Stripe record means a verified paid test Checkout session, not bank payout settlement. Historical local records were preserved rather than deleted to stage a cleaner screenshot.

| Image | Actual screen |
|---|---|
| [Workspace](workspace.jpg) | Local authenticated payment operations |
| [Stripe Checkout](stripe-checkout.jpg) | USD 3.00 hosted sandbox form before submission |
| [Transaction detail](transaction-detail.jpg) | Verified USD 3.00 Stripe test payment |
| [API docs](api-docs.jpg) | Live integration schema |
| [Provider reports](webhooks.jpg) | Processed actual Stripe notifications |
| [Transactions](transactions.jpg) | Stored Stripe test records |
| [Reconciliation detail](reconciliation-detail.jpg) | Six-row staged statement with five deliberate differences |
| [Reconciliation history](reconciliation-runs.jpg) | Actual completed comparison runs |
| [Prometheus](prometheus.jpg) | API target successfully scraped |
| [Grafana](grafana.jpg) | Provisioned database-backed monitoring |

Assertions and measured results are in [verification.md](../verification.md). Reproduce the flows using [local-demo.md](../local-demo.md). No API secret, signing secret or authentication token is included in the published screenshots.

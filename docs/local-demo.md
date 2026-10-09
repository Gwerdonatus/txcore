# Repeatable local walkthrough

Use the `docs/recruiter-walkthrough` branch until PR #1 is merged. Keep `.env` private and ignored. No real customer or card details are needed.

## Start the workspace

```sh
cp .env.example .env
chmod 600 .env
docker compose -p txcore config --quiet
docker compose -p txcore up -d --build --wait --wait-timeout 300
docker compose -p txcore exec web python manage.py setup_demo
```

Open http://localhost:8100/ and sign in as **demo.admin / TxCoreSandbox123!**. An existing account password is preserved. For a custom initial password, supply `TXCORE_DEMO_PASSWORD` when running the command and scripts. A new staff account receives read-only model-view permissions; application APIs use staff authorization.

## Pure local simulation

```sh
python3 scripts/demo.py
python3 scripts/demo.py
```

This authenticates, creates three explicitly synthetic USD records, retries each request, submits a valid and invalid generic demo signature, waits for the stored event to be processed and uploads four statement rows. It asserts one match and three discrepancies: amount, status and missing reference.

The second run reuses the three transactions. Each upload creates a new historical reconciliation run, so the entire script is not a no-op. Demo events are reporting only; records remain pending. No provider request or funds movement occurs. Do not dispatch settlement against these three records before repeating the script: its statement intentionally expects their pending states.

## Stripe test Checkout

Privately place the existing Stripe **test** secret in `STRIPE_SECRET_KEY` in `.env`. Live keys are rejected. Do not paste keys into screenshots, source code or issue bodies.

```sh
docker compose -p txcore --profile stripe up -d --build --wait --wait-timeout 300
python3 scripts/configure_stripe.py
docker compose -p txcore --profile stripe up -d --force-recreate --no-deps --wait web worker
```

The official Stripe CLI forwards selected Checkout events to the internal receiver. The configuration script saves its latest listener signing secret into `.env` without printing it. Re-run that script and recreate web/worker if the listener's signing secret changes. The internal hostname `web` must remain in `ALLOWED_HOSTS`.

1. Sign in to the workspace. Enter USD 3.00 and a description, then select **Continue to Stripe**.
2. Confirm Checkout says **Sandbox**. Use Stripe's public test card **4242 4242 4242 4242**, a future expiry and any three-digit CVC. Use a synthetic buyer, such as buyer@example.com. Leave saved-payment-information options unchecked.
3. Submit the test payment. After redirect, TxCore polls for verified state; if still processing, refresh after the next worker cycle.
4. Inspect the transaction link and provider report. Expect `settled` and a processed `checkout.session.completed` receipt. A missed receipt can instead be recovered from current Stripe state by the scheduled scan.

The API-only smoke command creates/reuses one test transaction and Checkout session without entering card details:

```sh
python3 -m scripts.stripe_smoke
```

## Reconcile an intentionally altered statement

Copy actual references from the workspace into a synthetic CSV. The supplied [sandbox statement example](sandbox-statement-example.csv) records the references used during verification; edit them for a fresh database. Upload it through **Statement reconciliation**. It should produce one match plus missing-reference, amount, currency, status and duplicate-reference differences.

The evidence shows CSV values as `expected` and database values as `actual`. Explain that convention while presenting the result. The file is staged test evidence, not a real provider payout statement.

## Operations

- Workspace: http://localhost:8100/
- API contract: http://localhost:8100/api/docs/
- Provider reports: http://localhost:8100/api/v1/webhooks/?provider=stripe
- Grafana: http://localhost:3010/d/txcore-sandbox/ (admin / admin locally)
- Prometheus targets: http://localhost:9091/targets

Nine core services run without the Stripe profile; the listener makes ten. Allow health checks to initialize. Use `docker compose -p txcore --profile stripe ps` and inspect failed service logs. Do not publish listener logs without redacting its signing secret. Never run `compose config` without `--quiet` in a shared transcript, because resolved environments contain credentials.

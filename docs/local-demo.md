# Repeatable local demonstration

All records are synthetic. No external API request, charge, transfer or account permission change occurs.

## Start

Use the branch and Compose commands in [the README](../README.md#run-locally). Startup performs migrations and collects static files. Allow service health checks to finish; a starting service is not a failure.

Run `python3 scripts/demo.py` from the repository on the host. The script only accepts localhost destinations. It creates three USD transactions with fixed idempotency keys, retries each request and checks the IDs, sends a valid and an invalid generic signed webhook, and uploads a four-row statement. It fails if expected HTTP statuses or reconciliation results do not match.

The first transaction creation returns 201. Repeating the demonstration returns 200 for the existing transactions. Webhook reports and reconciliation runs are new evidence for each execution; those operations are not deduplicated. This command does not reset the database.

The script uses the Compose demonstration webhook secret by default. For a different local secret, set `WEBHOOK_SECRET` for the script to match the API. Never publish an actual integration secret.

## Inspect the result

1. Open `http://localhost:8100/api/docs/` to inspect the real schema.
2. Open `/api/v1/transactions/` and follow the `transaction_reference` printed by the script to `/api/v1/transactions/<reference>/`.
3. Open `/api/v1/webhooks/?provider=demo` to inspect an accepted report. Its status remains `received`; it is not a processed provider notification.
4. Open the `reconciliation_detail_url` printed by the script. Show one match and three discrepancies: amount mismatch, status mismatch and absent transaction.
5. Open `http://localhost:9091/targets` to verify the API scrape is UP. Counts are local observations, not throughput claims.

The statement uses equal currencies deliberately. The current engine does not compare currency despite requiring the column.

## Verify the worker separately

```sh
docker compose -p txcore exec web python scripts/demo_settlement.py
```

This creates or reuses a separate EUR demo record and dispatches `workers.process_settlement` through Redis to Celery. It waits for the stored status to become settled. It does not call a provider. If already settled, the command reports that state without creating another record.

The fixed reference is `TXN-DEMO-SETTLEMENT`, separate from the three reconciliation inputs. View `/api/v1/transactions/TXN-DEMO-SETTLEMENT/` for the simulated outcome.

## Checks

Use the disposable test container in the README. Do not run test data against the development database. Run flake8 with `--max-line-length=110 --exclude=migrations`, matching CI. Validate OpenAPI with `python manage.py spectacular --validate --fail-on-warn` inside the web container.

The legacy `scripts/seed.py` remains available, but it creates additional random records on every invocation and is not the reproducible workflow shown in these screenshots.

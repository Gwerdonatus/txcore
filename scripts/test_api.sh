#!/bin/bash
# Asserted authenticated local smoke test. No secrets are printed.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 scripts/demo.py --base-url "${BASE_URL:-http://localhost:8100}"

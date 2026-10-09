"""Capture the local Stripe listener signing secret without printing credentials."""
import os
import re
import subprocess
import time
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    path = root / ".env"
    for _ in range(60):
        result = subprocess.run(
            ["docker", "compose", "-p", "txcore", "--profile", "stripe", "logs", "--no-color", "stripe-listener"],
            cwd=root, capture_output=True, text=True, check=True,
        )
        matches = re.findall(r"whsec_[a-zA-Z0-9]+", result.stdout)
        if matches:
            text = path.read_text()
            line = "STRIPE_WEBHOOK_SECRET=" + matches[-1]
            if re.search(r"^STRIPE_WEBHOOK_SECRET=.*$", text, re.M):
                text = re.sub(r"^STRIPE_WEBHOOK_SECRET=.*$", line, text, flags=re.M)
            else:
                text += "\n" + line + "\n"
            path.write_text(text)
            os.chmod(path, 0o600)
            print("Stripe listener signing secret saved privately. Recreate API and worker to apply it.")
            return
        time.sleep(1)
    raise RuntimeError("Stripe listener did not become ready. Check account authentication and network access.")


if __name__ == "__main__":
    main()

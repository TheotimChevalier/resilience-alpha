"""Authorized resilience exercise. Run only against the team's own lab."""

import os
import sys
import time

import requests

TARGET_HOST = os.getenv("TARGET_HOST", "192.168.137.1")
WAF_URL = os.getenv("WAF_URL", f"http://{TARGET_HOST}")
AUTH_URL = os.getenv("AUTH_URL", f"http://{TARGET_HOST}:8080/auth")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", f"http://{TARGET_HOST}:8080")
USERNAME = os.getenv("OPERATOR_USERNAME")
PASSWORD = os.getenv("OPERATOR_PASSWORD")
REMEDIATION_TOKEN = os.getenv("REMEDIATION_TOKEN")


def require_configuration():
    missing = [
        name
        for name, value in (
            ("OPERATOR_USERNAME", USERNAME),
            ("OPERATOR_PASSWORD", PASSWORD),
            ("REMEDIATION_TOKEN", REMEDIATION_TOKEN),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


def run_attack():
    require_configuration()
    print(f"[*] Authorized resilience exercise against {TARGET_HOST} (WAF {WAF_URL})")
    print(f"[*] Dashboard: {DASHBOARD_URL}")
    token_response = requests.post(
        f"{AUTH_URL}/token",
        json={"username": USERNAME, "password": PASSWORD},
        timeout=5,
    )
    token_response.raise_for_status()
    operator_token = token_response.json()["access_token"]

    injection = requests.post(
        f"{WAF_URL}/admin/inject-fault",
        headers={"X-Remediation-Token": REMEDIATION_TOKEN},
        timeout=5,
    )
    injection.raise_for_status()
    incident = injection.json()["incident_id"]
    print(f"[+] Controlled incident {incident} injected.")

    failures = 0
    for attempt in range(8):
        try:
            response = requests.post(
                f"{WAF_URL}/api/v1/pay",
                headers={"Authorization": f"Bearer {operator_token}"},
                json={
                    "user_id": f"REDTEAM-{attempt + 1}",
                    "amount": 1.0,
                    "destination_account": "LAB-ONLY",
                },
                timeout=5,
            )
            if response.status_code == 503:
                failures += 1
                print(f"[!] Payment correctly unavailable during incident ({attempt + 1}/8).")
            elif response.ok:
                print("[+] Service recovered while the exercise was running.")
                break
            else:
                print(f"[-] Unexpected payment response: HTTP {response.status_code}.")
        except requests.RequestException as exc:
            print(f"[-] Payment request failed: {exc}")
        time.sleep(0.25)

    if failures == 0:
        raise RuntimeError("The service did not expose the injected fault to the payment route.")

    print("[*] Waiting up to 90 seconds for ML detection and verified recovery.")
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            health = requests.get(f"{WAF_URL}/health", timeout=3)
            if health.ok and health.json().get("status") == "ok":
                check = requests.post(
                    f"{WAF_URL}/api/v1/pay",
                    headers={"Authorization": f"Bearer {operator_token}"},
                    json={
                        "user_id": "REDTEAM-POST-RECOVERY",
                        "amount": 0.02,
                        "destination_account": "LAB-ONLY",
                    },
                    timeout=5,
                )
                check.raise_for_status()
                print(f"[+] Service recovered; verification payment {check.json()['transaction_id']} succeeded.")
                return
        except requests.RequestException:
            pass
        time.sleep(2)

    raise TimeoutError("AIOps did not restore the service within 90 seconds; inspect Grafana and AIOps logs.")


if __name__ == "__main__":
    try:
        run_attack()
    except (RuntimeError, TimeoutError, requests.RequestException) as error:
        print(f"[x] Exercise failed: {error}", file=sys.stderr)
        sys.exit(1)

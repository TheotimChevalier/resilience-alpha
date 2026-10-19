import logging
import os
import time

import numpy as np
import requests
from sklearn.ensemble import IsolationForest

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
PAYMENT_API_URL = os.getenv("PAYMENT_API_URL", "http://payment-api:8000")
AUTH_URL = os.getenv("AUTH_URL", "http://auth:8001")
OPERATOR_USERNAME = os.getenv("OPERATOR_USERNAME")
OPERATOR_PASSWORD = os.getenv("OPERATOR_PASSWORD")
REMEDIATION_TOKEN = os.getenv("REMEDIATION_TOKEN")
POLL_SECONDS = float(os.getenv("POLL_SECONDS", "3"))
MIN_FAILED_PAYMENTS = int(os.getenv("MIN_FAILED_PAYMENTS", "3"))
REMEDIATION_RETRY_SECONDS = float(os.getenv("REMEDIATION_RETRY_SECONDS", "15"))

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [AIOps] %(message)s",
)
logger = logging.getLogger("aiops")

FEATURE_QUERIES = {
    "request_count": "sum(increase(resilience_payment_requests_total[1m])) or vector(0)",
    "error_ratio": (
        "(sum(increase(resilience_payment_requests_total{status=~\"5..\"}[1m])) "
        "/ clamp_min(sum(increase(resilience_payment_requests_total[1m])), 1)) or vector(0)"
    ),
    "mean_latency": (
        "(sum(increase(resilience_payment_duration_seconds_sum[1m])) "
        "/ clamp_min(sum(increase(resilience_payment_duration_seconds_count[1m])), 1)) or vector(0.1)"
    ),
}


def train_detector() -> IsolationForest:
    rng = np.random.default_rng(42)
    request_count = rng.poisson(lam=3.0, size=800)
    error_ratio = rng.beta(a=0.6, b=35, size=800)
    mean_latency = rng.normal(loc=0.1, scale=0.025, size=800).clip(0.025, 0.25)
    baseline = np.column_stack((request_count, error_ratio, mean_latency))
    detector = IsolationForest(contamination=0.025, random_state=42)
    detector.fit(baseline)
    return detector


def query_feature(query: str) -> float:
    response = requests.get(
        f"{PROMETHEUS_URL}/api/v1/query",
        params={"query": query},
        timeout=4,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {payload.get('error', 'unknown error')}")
    values = payload["data"]["result"]
    return float(values[0]["value"][1]) if values else 0.0


def collect_features() -> dict[str, float]:
    return {name: query_feature(query) for name, query in FEATURE_QUERIES.items()}


def authenticate() -> str:
    if not OPERATOR_USERNAME or not OPERATOR_PASSWORD:
        raise RuntimeError("OPERATOR_USERNAME and OPERATOR_PASSWORD must be set")
    response = requests.post(
        f"{AUTH_URL}/token",
        json={"username": OPERATOR_USERNAME, "password": OPERATOR_PASSWORD},
        timeout=5,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def verify_recovery(token: str) -> tuple[bool, str | None, str]:
    health = requests.get(f"{PAYMENT_API_URL}/health", timeout=5)
    health.raise_for_status()
    if health.json().get("status") != "ok":
        return False, None, "Post-remediation health check reports a degraded API."

    response = requests.post(
        f"{PAYMENT_API_URL}/api/v1/pay",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_id": "AIOPS-RECOVERY-CHECK",
            "amount": 0.01,
            "destination_account": "INTERNAL-TEST",
        },
        timeout=8,
    )
    response.raise_for_status()
    transaction_id = response.json()["transaction_id"]
    return True, transaction_id, f"Health check passed and recovery payment {transaction_id} succeeded."


def remediate() -> bool:
    headers = {"X-Remediation-Token": REMEDIATION_TOKEN or ""}
    response = requests.post(
        f"{PAYMENT_API_URL}/admin/remediate",
        headers=headers,
        timeout=5,
    )
    response.raise_for_status()
    token = authenticate()

    recovered = False
    transaction_id = None
    message = "Recovery could not be verified."
    for attempt in range(1, 6):
        try:
            recovered, transaction_id, message = verify_recovery(token)
            if recovered:
                break
        except requests.RequestException as exc:
            message = f"Recovery check {attempt}/5 failed: {exc}"
            logger.warning(message)
            time.sleep(2)

    result = requests.post(
        f"{PAYMENT_API_URL}/ops/recovery-result",
        headers=headers,
        json={
            "recovered": recovered,
            "check_transaction_id": transaction_id,
            "message": message,
        },
        timeout=5,
    )
    result.raise_for_status()
    if recovered:
        logger.info("%s", message)
    else:
        logger.error("%s", message)
    return recovered


def should_attempt_remediation(
    anomaly: bool,
    enough_evidence: bool,
    incident_active: bool,
    recovery_verified: bool,
    last_remediation_attempt: float,
    now: float,
) -> bool:
    if not enough_evidence:
        return False
    if not incident_active:
        return anomaly
    return (
        not recovery_verified
        and now - last_remediation_attempt >= REMEDIATION_RETRY_SECONDS
    )


def main():
    model = train_detector()
    logger.info(
        "IsolationForest trained on 800 synthetic nominal observations; features: request count, "
        "HTTP 5xx ratio, and mean payment latency."
    )
    logger.info("Monitoring Prometheus at %s every %.1fs.", PROMETHEUS_URL, POLL_SECONDS)
    incident_active = False
    recovery_verified = False
    last_remediation_attempt = 0.0

    while True:
        try:
            features = collect_features()
            sample = np.array(
                [[features["request_count"], features["error_ratio"], features["mean_latency"]]]
            )
            anomaly = model.predict(sample)[0] == -1
            enough_evidence = (
                features["error_ratio"] >= 0.25
                and features["request_count"] >= MIN_FAILED_PAYMENTS
            )
            logger.debug("ML observation: %s; anomaly=%s; actionable=%s", features, anomaly, enough_evidence)
            if should_attempt_remediation(
                anomaly,
                enough_evidence,
                incident_active,
                recovery_verified,
                last_remediation_attempt,
                time.monotonic(),
            ):
                retrying = incident_active
                incident_active = True
                last_remediation_attempt = time.monotonic()
                if retrying:
                    logger.warning("Retrying remediation after the previous recovery check failed.")
                else:
                    logger.warning("Anomaly detected from measured features: %s", features)
                recovery_verified = remediate()
            elif incident_active and recovery_verified and features["error_ratio"] < 0.05:
                incident_active = False
                recovery_verified = False
                logger.info("Measured service signals returned to baseline.")
        except (requests.RequestException, RuntimeError, ValueError, KeyError) as exc:
            logger.error("Monitoring iteration failed; no remediation was attempted: %s", exc)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()

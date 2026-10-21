import logging
import os
import time

import numpy as np
import requests
from sklearn.ensemble import IsolationForest

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
PAYMENT_API_URL = os.getenv("PAYMENT_API_URL", "http://payment-api:8000")
AUTH_URL = os.getenv("AUTH_URL", "http://auth:8001")
REMEDIATION_TOKEN = os.getenv("REMEDIATION_TOKEN")
AIOPS_CLIENT_SECRET = os.getenv("AIOPS_CLIENT_SECRET")
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


def generate_nominal_observations(sample_count: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    request_count = rng.poisson(lam=3.0, size=sample_count)
    error_ratio = rng.beta(a=0.6, b=35, size=sample_count)
    mean_latency = rng.normal(loc=0.1, scale=0.025, size=sample_count).clip(0.025, 0.25)
    idle = request_count == 0
    error_ratio[idle] = 0.0
    mean_latency[idle] = 0.0
    return np.column_stack((request_count, error_ratio, mean_latency))


def generate_evaluation_data(
    nominal_count: int = 400,
    incident_count: int = 200,
    seed: int = 2026,
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    nominal = generate_nominal_observations(nominal_count, seed)
    incident = np.column_stack(
        (
            rng.poisson(lam=10.0, size=incident_count),
            rng.beta(a=10, b=2, size=incident_count),
            rng.normal(loc=0.12, scale=0.025, size=incident_count).clip(0.025, 0.25),
        )
    )
    observations = np.vstack((nominal, incident))
    labels = np.concatenate(
        (np.zeros(nominal_count, dtype=int), np.ones(incident_count, dtype=int))
    )
    return observations, labels


def train_detector() -> IsolationForest:
    detector = IsolationForest(contamination=0.01, random_state=42)
    detector.fit(generate_nominal_observations(sample_count=800, seed=42))
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
    if not AIOPS_CLIENT_SECRET:
        raise RuntimeError("AIOPS_CLIENT_SECRET must be set")
    response = requests.post(
        f"{AUTH_URL}/service/token",
        json={"client_id": "aiops-detector", "client_secret": AIOPS_CLIENT_SECRET},
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


def report_detection(features: dict[str, float], anomaly_score: float) -> None:
    response = requests.post(
        f"{PAYMENT_API_URL}/ops/detection",
        headers={"X-Remediation-Token": REMEDIATION_TOKEN or ""},
        json={
            "model_anomaly": True,
            "actionable": True,
            "anomaly_score": anomaly_score,
            **features,
        },
        timeout=5,
    )
    response.raise_for_status()


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
        "IsolationForest trained on 800 deterministic synthetic nominal observations "
        "(seed=42; contamination=0.01); features: request count, HTTP 5xx ratio, "
        "and mean payment latency."
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
            anomaly_score = float(model.decision_function(sample)[0])
            enough_evidence = (
                features["error_ratio"] >= 0.25
                and features["request_count"] >= MIN_FAILED_PAYMENTS
            )
            actionable = anomaly and enough_evidence
            logger.debug(
                "ML observation: features=%s; anomaly=%s; score=%.6f; actionable=%s",
                features,
                anomaly,
                anomaly_score,
                actionable,
            )
            if should_attempt_remediation(
                anomaly,
                enough_evidence,
                incident_active,
                recovery_verified,
                last_remediation_attempt,
                time.monotonic(),
            ):
                retrying = incident_active
                if not retrying:
                    report_detection(features, anomaly_score)
                incident_active = True
                last_remediation_attempt = time.monotonic()
                if retrying:
                    logger.warning("Retrying remediation after the previous recovery check failed.")
                else:
                    logger.warning(
                        "ML anomaly detected; score=%.6f; features=%s; remediation "
                        "evidence gate passed.",
                        anomaly_score,
                        features,
                    )
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

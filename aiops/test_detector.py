import numpy as np

from detector import (
    authenticate,
    collect_features,
    generate_evaluation_data,
    report_detection,
    should_attempt_remediation,
    train_detector,
)


def test_isolation_forest_separates_extreme_payment_failures():
    detector = train_detector()
    nominal = np.array([[1.0, 0.0, 0.1], [3.0, 0.01, 0.12]])
    incident = np.array([[8.0, 0.95, 0.12]])
    assert (detector.predict(nominal) == 1).all()
    assert detector.predict(incident)[0] == -1


def test_synthetic_evaluation_measures_false_positives_and_false_negatives():
    detector = train_detector()
    observations, labels = generate_evaluation_data()
    predictions = detector.predict(observations)

    false_positives = ((labels == 0) & (predictions == -1)).sum()
    false_negatives = ((labels == 1) & (predictions == 1)).sum()
    false_positive_rate = false_positives / (labels == 0).sum()
    false_negative_rate = false_negatives / (labels == 1).sum()

    assert false_positive_rate <= 0.05
    assert false_negative_rate <= 0.05


def test_action_gate_requires_both_anomaly_and_payment_failure_evidence():
    assert not should_attempt_remediation(
        anomaly=False,
        enough_evidence=True,
        incident_active=False,
        recovery_verified=False,
        last_remediation_attempt=0.0,
        now=10.0,
    )
    assert not should_attempt_remediation(
        anomaly=True,
        enough_evidence=False,
        incident_active=False,
        recovery_verified=False,
        last_remediation_attempt=0.0,
        now=10.0,
    )


def test_model_decision_is_sent_to_the_protected_api_route(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            pass

    def post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("detector.requests.post", post)
    monkeypatch.setattr("detector.PAYMENT_API_URL", "http://payment-api")
    monkeypatch.setattr("detector.REMEDIATION_TOKEN", "test-remediation-token")

    report_detection(
        {"request_count": 8.0, "error_ratio": 0.875, "mean_latency": 0.12},
        anomaly_score=-0.15,
    )

    assert captured["url"] == "http://payment-api/ops/detection"
    assert captured["headers"] == {"X-Remediation-Token": "test-remediation-token"}
    assert captured["json"] == {
        "model_anomaly": True,
        "actionable": True,
        "anomaly_score": -0.15,
        "request_count": 8.0,
        "error_ratio": 0.875,
        "mean_latency": 0.12,
    }


def test_detector_authenticates_with_its_service_secret(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"access_token": "service-token"}

    def post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("detector.requests.post", post)
    monkeypatch.setattr("detector.AUTH_URL", "http://auth")
    monkeypatch.setattr("detector.AIOPS_CLIENT_SECRET", "test-aiops-client-secret")

    assert authenticate() == "service-token"
    assert captured["url"] == "http://auth/service/token"
    assert captured["json"] == {
        "client_id": "aiops-detector",
        "client_secret": "test-aiops-client-secret",
    }


def test_incident_window_prometheus_queries_avoid_nan_values(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "status": "success",
                "data": {"result": [{"value": [0, "0"]}]},
            }

    monkeypatch.setattr("detector.requests.get", lambda *_args, **_kwargs: Response())
    features = collect_features()
    assert features == {"request_count": 0.0, "error_ratio": 0.0, "mean_latency": 0.0}


def test_verified_recovery_is_not_remediated_again_while_incident_window_is_high():
    assert should_attempt_remediation(
        anomaly=True,
        enough_evidence=True,
        incident_active=False,
        recovery_verified=False,
        last_remediation_attempt=0.0,
        now=10.0,
    )
    assert not should_attempt_remediation(
        anomaly=True,
        enough_evidence=True,
        incident_active=True,
        recovery_verified=True,
        last_remediation_attempt=10.0,
        now=40.0,
    )


def test_failed_recovery_can_retry_only_after_cooldown():
    assert not should_attempt_remediation(
        anomaly=True,
        enough_evidence=True,
        incident_active=True,
        recovery_verified=False,
        last_remediation_attempt=10.0,
        now=24.0,
    )
    assert should_attempt_remediation(
        anomaly=True,
        enough_evidence=True,
        incident_active=True,
        recovery_verified=False,
        last_remediation_attempt=10.0,
        now=25.0,
    )

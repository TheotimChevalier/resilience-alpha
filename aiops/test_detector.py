import numpy as np

from detector import collect_features, should_attempt_remediation, train_detector


def test_isolation_forest_separates_extreme_payment_failures():
    detector = train_detector()
    nominal = np.array([[1.0, 0.0, 0.1], [3.0, 0.01, 0.12]])
    incident = np.array([[8.0, 0.95, 0.12]])
    assert (detector.predict(nominal) == 1).all()
    assert detector.predict(incident)[0] == -1


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

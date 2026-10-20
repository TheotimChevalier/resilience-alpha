import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["EXERCISE_TOKEN"] = "test-exercise-token-that-is-long-enough"
os.environ["AUTH_SIGNING_SECRET"] = "test-only-signing-secret-with-more-than-32-characters"
os.environ["REMEDIATION_TOKEN"] = "test-remediation-token-that-is-long-enough"

from fastapi.testclient import TestClient

from api import main


client = TestClient(main.app)
main.push_log_to_loki = lambda *_args, **_kwargs: None


def operator_token():
    header = main._b64url(b'{"alg":"HS256","typ":"JWT"}')
    payload = main._b64url(
        b'{"iss":"resilience-auth","sub":"test-operator","exp":4102444800}'
    )
    signed = f"{header}.{payload}".encode("ascii")
    signature = main._b64url(
        main.hmac.new(
            main.TOKEN_SECRET.encode(),
            signed,
            main.hashlib.sha256,
        ).digest()
    )
    return f"{header}.{payload}.{signature}"


def test_controlled_incident_is_detectable_and_recoverable():
    main.Base.metadata.drop_all(bind=main.engine)
    main.Base.metadata.create_all(bind=main.engine)
    with main.state_lock:
        main.INCIDENTS.clear()
        main.injected_fault_until = 0
        main.active_incident_id = None

    assert client.get("/health").json()["status"] == "ok"
    before_incident = client.post(
        "/api/v1/pay",
        headers={"Authorization": f"Bearer {operator_token()}"},
        json={
            "user_id": "TEST-OPERATOR",
            "amount": 1.0,
            "destination_account": "LAB-ONLY",
        },
    )
    assert before_incident.status_code == 200
    assert client.post(
        "/admin/inject-fault",
        headers={"X-Exercise-Token": "incorrect"},
    ).status_code == 403
    assert client.post(
        "/admin/inject-fault",
        headers={"X-Remediation-Token": main.REMEDIATION_TOKEN},
    ).status_code == 403
    injection = client.post(
        "/admin/inject-fault",
        headers={"X-Exercise-Token": main.EXERCISE_TOKEN},
    )
    assert injection.status_code == 202
    incident_id = injection.json()["incident_id"]
    assert client.post(
        "/admin/inject-fault",
        headers={"X-Exercise-Token": main.EXERCISE_TOKEN},
    ).status_code == 409

    payment = {
        "user_id": "TEST-OPERATOR",
        "amount": 1.0,
        "destination_account": "LAB-ONLY",
    }
    assert client.post("/api/v1/pay", json=payment).status_code == 401
    operator_headers = {"Authorization": f"Bearer {operator_token()}"}
    failed = client.post("/api/v1/pay", headers=operator_headers, json=payment)
    assert failed.status_code == 503
    assert client.get("/health").json() == {"status": "degraded", "incident_active": True}

    assert client.post(
        "/admin/remediate",
        headers={"X-Exercise-Token": main.EXERCISE_TOKEN},
    ).status_code == 403
    assert client.post(
        "/ops/recovery-result",
        headers={"X-Exercise-Token": main.EXERCISE_TOKEN},
        json={"recovered": True, "message": "unauthorized"},
    ).status_code == 403
    detection = client.post(
        "/ops/detection",
        headers={"X-Remediation-Token": main.REMEDIATION_TOKEN},
        json={
            "model_anomaly": True,
            "actionable": True,
            "anomaly_score": -0.15,
            "request_count": 8,
            "error_ratio": 0.875,
            "mean_latency": 0.12,
        },
    )
    assert detection.status_code == 202

    assert client.post(
        "/admin/remediate",
        headers={"X-Remediation-Token": main.REMEDIATION_TOKEN},
    ).json()["incident_id"] == incident_id
    assert client.post(
        "/admin/remediate",
        headers={"X-Remediation-Token": main.REMEDIATION_TOKEN},
    ).json()["status"] == "already_nominal"
    recovered = client.post("/api/v1/pay", headers=operator_headers, json=payment)
    assert recovered.status_code == 200
    transaction_id = recovered.json()["transaction_id"]
    assert transaction_id.startswith("TXN-")

    result = client.post(
        "/ops/recovery-result",
        headers={"X-Remediation-Token": main.REMEDIATION_TOKEN},
        json={
            "recovered": True,
            "check_transaction_id": transaction_id,
            "message": "Health and test payment succeeded.",
        },
    )
    assert result.status_code == 200
    state = client.get("/ops/state", headers=operator_headers)
    assert state.status_code == 200
    assert state.json()["api"] == "operational"
    assert state.json()["incident_phase"] == "recovered"
    assert state.json()["latest_detection"]["actionable"] is True
    assert state.json()["transactions"] == 2
    assert state.json()["volume"] == 2.0
    assert any(event["type"] == "incident" for event in state.json()["events"])
    assert any(
        event["type"] == "authorization_denied" and event["actor"] == "unknown"
        for event in state.json()["events"]
    )
    assert any(
        event["type"] == "exercise_rejected"
        and event["actor"] == "redteam-exercise"
        for event in state.json()["events"]
    )
    assert any(
        event["type"] == "detection"
        and event["actor"] == "aiops-detector"
        and event["actionable"]
        for event in state.json()["events"]
    )
    assert any(
        event["type"] == "remediation" and event["actor"] == "aiops-detector"
        for event in state.json()["events"]
    )
    assert any(event["type"] == "recovery" for event in state.json()["events"])
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "resilience_incident_active 0.0" in metrics.text
    assert "resilience_model_anomaly 1.0" in metrics.text
    assert "resilience_recovery_verified 1.0" in metrics.text


def test_tampered_operator_token_is_rejected():
    response = client.get(
        "/ops/state",
        headers={"Authorization": "Bearer header.payload.invalid"},
    )
    assert response.status_code == 401

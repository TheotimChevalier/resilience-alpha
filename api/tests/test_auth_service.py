import os
import tempfile
from pathlib import Path

os.environ["AUTH_SIGNING_SECRET"] = "test-only-signing-secret-with-more-than-32-characters"
os.environ["OPERATOR_USERNAME"] = "test-operator"
os.environ["OPERATOR_PASSWORD"] = "test-password-that-is-long-enough"
os.environ["FACE_AGENT_TOKEN"] = "test-face-agent-token-with-more-than-32-characters"
os.environ["AIOPS_CLIENT_SECRET"] = "test-aiops-client-secret-with-more-than-32-characters"
os.environ["AUTH_DB_PATH"] = str(Path(tempfile.gettempdir()) / "resilience-alpha-auth-test.db")
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["EXERCISE_TOKEN"] = "test-exercise-token-that-is-long-enough"
os.environ["REMEDIATION_TOKEN"] = "test-remediation-token-that-is-long-enough"

from fastapi.testclient import TestClient

from api import main as payment_api
from auth import main as auth_service


client = TestClient(auth_service.app)


def test_face_check_then_password_issues_an_api_token(monkeypatch):
    monkeypatch.setattr(auth_service, "_face_agent", lambda *args, **kwargs: {"recognized": True})
    monkeypatch.setattr(auth_service, "_publish_led", lambda *_: None)
    with auth_service._connect() as connection:
        connection.execute("DELETE FROM face_failures WHERE username = 'test-operator'")
    challenge = client.post(
        "/face/verify",
        json={"username": os.environ["OPERATOR_USERNAME"]},
    )
    assert challenge.status_code == 200

    response = client.post(
        "/token",
        json={
            "username": os.environ["OPERATOR_USERNAME"],
            "password": os.environ["OPERATOR_PASSWORD"],
            "challenge_id": challenge.json()["challenge_id"],
        },
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert payment_api.require_operator(f"Bearer {token}") == "test-operator"


def test_auth_service_rejects_invalid_password_after_face_check(monkeypatch):
    monkeypatch.setattr(auth_service, "_face_agent", lambda *args, **kwargs: {"recognized": True})
    monkeypatch.setattr(auth_service, "_publish_led", lambda *_: None)
    with auth_service._connect() as connection:
        connection.execute("DELETE FROM face_failures WHERE username = 'test-operator'")
    challenge = client.post(
        "/face/verify",
        json={"username": os.environ["OPERATOR_USERNAME"]},
    )
    assert challenge.status_code == 200
    response = client.post(
        "/token",
        json={
            "username": "test-operator",
            "password": "incorrect",
            "challenge_id": challenge.json()["challenge_id"],
        },
    )
    assert response.status_code == 401


def test_face_mismatch_allows_one_retry_then_locks_for_five_minutes(monkeypatch):
    monkeypatch.setattr(auth_service, "_face_agent", lambda *args, **kwargs: {"recognized": False})
    monkeypatch.setattr(auth_service, "_publish_led", lambda *_: None)
    with auth_service._connect() as connection:
        connection.execute("DELETE FROM face_failures WHERE username = 'test-operator'")

    first = client.post("/face/verify", json={"username": "test-operator"})
    second = client.post("/face/verify", json={"username": "test-operator"})

    assert first.status_code == 401
    assert first.headers["Retry-After"] == "30"
    assert second.status_code == 423
    assert second.headers["Retry-After"] == "300"


def test_missing_face_is_counted_as_a_failed_identification(monkeypatch):
    def no_face(*_args, **_kwargs):
        raise auth_service.HTTPException(422, "No face detected")

    monkeypatch.setattr(auth_service, "_face_agent", no_face)
    led_states = []
    monkeypatch.setattr(auth_service, "_publish_led", led_states.append)
    with auth_service._connect() as connection:
        connection.execute("DELETE FROM face_failures WHERE username = 'test-operator'")

    response = client.post("/face/verify", json={"username": "test-operator"})

    assert response.status_code == 401
    assert response.headers["Retry-After"] == "30"
    assert led_states == ["face_denied"]


def test_aiops_service_token_requires_its_dedicated_secret():
    valid = client.post(
        "/service/token",
        json={
            "client_id": "aiops-detector",
            "client_secret": os.environ["AIOPS_CLIENT_SECRET"],
        },
    )
    assert valid.status_code == 200
    assert valid.json()["role"] == "operator"

    invalid = client.post(
        "/service/token",
        json={"client_id": "aiops-detector", "client_secret": "incorrect"},
    )
    assert invalid.status_code == 401


def test_admin_manages_user_account_and_face_profile(monkeypatch):
    face_users = set()

    def fake_face_agent(path, *, method="GET", payload=None):
        if path == "/users":
            return {"users": sorted(face_users)}
        if path == "/users/enroll":
            face_users.add(payload["username"])
            return {"username": payload["username"], "samples": 8}
        if method == "DELETE":
            face_users.discard(path.removeprefix("/users/"))
            return {"face_profile_removed": True}
        raise AssertionError(f"Unexpected face-agent request: {method} {path}")

    monkeypatch.setattr(auth_service, "_face_agent", fake_face_agent)
    with auth_service._connect() as connection:
        connection.execute("DELETE FROM users WHERE username = 'managed-user'")

    admin_token = auth_service._issue_token("test-operator", "admin")["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    created = client.post(
        "/admin/users",
        headers=admin_headers,
        json={"username": "managed-user", "password": "managed-password-long-enough", "role": "operator"},
    )
    assert created.status_code == 201

    operator_token = auth_service._issue_token("managed-user", "operator")["access_token"]
    denied = client.get("/admin/users", headers={"Authorization": f"Bearer {operator_token}"})
    assert denied.status_code == 403

    enrolled = client.post("/admin/users/managed-user/face", headers=admin_headers)
    assert enrolled.status_code == 200
    assert enrolled.json()["samples"] == 8

    listed = client.get("/admin/users", headers=admin_headers)
    managed = next(user for user in listed.json()["users"] if user["username"] == "managed-user")
    assert managed["face_enrolled"] is True

    deleted = client.delete("/admin/users/managed-user", headers=admin_headers)
    assert deleted.status_code == 200
    assert "managed-user" not in face_users

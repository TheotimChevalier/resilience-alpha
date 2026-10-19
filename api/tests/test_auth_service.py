import os

os.environ["AUTH_SIGNING_SECRET"] = "test-only-signing-secret-with-more-than-32-characters"
os.environ["OPERATOR_USERNAME"] = "test-operator"
os.environ["OPERATOR_PASSWORD"] = "test-password-that-is-long-enough"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["REMEDIATION_TOKEN"] = "test-remediation-token-that-is-long-enough"

from fastapi.testclient import TestClient

from api import main as payment_api
from auth import main as auth_service


client = TestClient(auth_service.app)


def test_auth_service_issues_a_token_accepted_by_payment_api():
    response = client.post(
        "/token",
        json={
            "username": os.environ["OPERATOR_USERNAME"],
            "password": os.environ["OPERATOR_PASSWORD"],
        },
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert payment_api.require_operator(f"Bearer {token}") == "test-operator"


def test_auth_service_rejects_invalid_credentials():
    response = client.post(
        "/token",
        json={"username": "test-operator", "password": "incorrect"},
    )
    assert response.status_code == 401

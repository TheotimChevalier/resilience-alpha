import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

SECRET = os.getenv("AUTH_SIGNING_SECRET")
USERNAME = os.getenv("OPERATOR_USERNAME")
PASSWORD = os.getenv("OPERATOR_PASSWORD")
if not SECRET or len(SECRET) < 32:
    raise RuntimeError("AUTH_SIGNING_SECRET must contain at least 32 characters")
if not USERNAME or not PASSWORD or len(PASSWORD) < 12:
    raise RuntimeError("Set OPERATOR_USERNAME and a 12-character OPERATOR_PASSWORD")

app = FastAPI(title="Resilience Alpha Operator Authentication", version="1.0.0")


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/token")
def issue_token(credentials: Credentials):
    valid_user = hmac.compare_digest(credentials.username, USERNAME)
    valid_password = hmac.compare_digest(credentials.password, PASSWORD)
    if not (valid_user and valid_password):
        raise HTTPException(status_code=401, detail="Identifiants invalides")

    header = _encode(b'{"alg":"HS256","typ":"JWT"}')
    payload = _encode(
        json.dumps(
            {
                "iss": "resilience-auth",
                "sub": credentials.username,
                "iat": int(time.time()),
                "exp": int(time.time()) + 3600,
            },
            separators=(",", ":"),
        ).encode()
    )
    signed = f"{header}.{payload}".encode("ascii")
    signature = _encode(hmac.new(SECRET.encode(), signed, hashlib.sha256).digest())
    return {"access_token": f"{header}.{payload}.{signature}", "token_type": "bearer", "expires_in": 3600}

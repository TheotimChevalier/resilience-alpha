import base64
import binascii
from contextlib import contextmanager
import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import time
from pathlib import Path
from urllib.parse import quote

from paho.mqtt import MQTTException
import paho.mqtt.publish as mqtt_publish
import requests
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

SECRET = os.getenv("AUTH_SIGNING_SECRET")
INITIAL_USERNAME = os.getenv("OPERATOR_USERNAME")
INITIAL_PASSWORD = os.getenv("OPERATOR_PASSWORD")
FACE_AGENT_URL = os.getenv("FACE_AGENT_URL", "http://host.docker.internal:8765").rstrip("/")
FACE_AGENT_TOKEN = os.getenv("FACE_AGENT_TOKEN")
AIOPS_CLIENT_SECRET = os.getenv("AIOPS_CLIENT_SECRET")
AUTH_DB_PATH = Path(os.getenv("AUTH_DB_PATH", "/data/auth.db"))
MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
CHALLENGE_TTL_SECONDS = 120
FACE_LOCK_SECONDS = 300
FACE_FAILURE_LIMIT = 2

if not SECRET or len(SECRET) < 32:
    raise RuntimeError("AUTH_SIGNING_SECRET must contain at least 32 characters")
if not INITIAL_USERNAME or not INITIAL_PASSWORD or len(INITIAL_PASSWORD) < 12:
    raise RuntimeError("Set OPERATOR_USERNAME and a 12-character OPERATOR_PASSWORD")
if not FACE_AGENT_TOKEN or len(FACE_AGENT_TOKEN) < 32:
    raise RuntimeError("FACE_AGENT_TOKEN must contain at least 32 characters")
if not AIOPS_CLIENT_SECRET or len(AIOPS_CLIENT_SECRET) < 32:
    raise RuntimeError("AIOPS_CLIENT_SECRET must contain at least 32 characters")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("auth")
app = FastAPI(title="Resilience Alpha Operator Authentication", version="2.0.0")
challenges: dict[str, tuple[str, float]] = {}


class UsernameRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)
    challenge_id: str = Field(min_length=16, max_length=80)


class ChallengeRequest(BaseModel):
    challenge_id: str = Field(min_length=16, max_length=80)


class ServiceCredentials(BaseModel):
    client_id: str = Field(min_length=1, max_length=80)
    client_secret: str = Field(min_length=1, max_length=256)


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=12, max_length=256)
    role: str = Field(pattern=r"^(admin|operator)$")


@contextmanager
def _connect():
    AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(AUTH_DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _hash_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    actual_salt = salt or secrets.token_bytes(16)
    return actual_salt, hashlib.pbkdf2_hmac("sha256", password.encode(), actual_salt, 310_000)


def _initialize_database() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY COLLATE NOCASE,
                salt BLOB NOT NULL,
                password_hash BLOB NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'operator')),
                active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS face_failures (
                username TEXT PRIMARY KEY COLLATE NOCASE,
                failures INTEGER NOT NULL DEFAULT 0,
                locked_until REAL NOT NULL DEFAULT 0
            )
            """
        )
        if connection.execute("SELECT 1 FROM users WHERE username = ?", (INITIAL_USERNAME,)).fetchone() is None:
            salt, digest = _hash_password(INITIAL_PASSWORD)
            connection.execute(
                "INSERT INTO users (username, salt, password_hash, role) VALUES (?, ?, ?, 'admin')",
                (INITIAL_USERNAME, salt, digest),
            )


_initialize_database()


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _issue_token(username: str, role: str) -> dict:
    now = time.time()
    for challenge_id, (_, expires_at) in list(challenges.items()):
        if expires_at <= now:
            challenges.pop(challenge_id, None)
    issued_at = int(time.time())
    header = _encode(b'{"alg":"HS256","typ":"JWT"}')
    payload = _encode(
        json.dumps(
            {
                "iss": "resilience-auth",
                "sub": username,
                "role": role,
                "iat": issued_at,
                "exp": issued_at + 3600,
            },
            separators=(",", ":"),
        ).encode()
    )
    signed = f"{header}.{payload}".encode("ascii")
    signature = _encode(hmac.new(SECRET.encode(), signed, hashlib.sha256).digest())
    return {
        "access_token": f"{header}.{payload}.{signature}",
        "token_type": "bearer",
        "expires_in": 3600,
        "username": username,
        "role": role,
    }


def _authenticate_request(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Operator bearer token required")
    try:
        header, payload, signature = authorization[7:].split(".")
        signed = f"{header}.{payload}".encode("ascii")
        expected = _encode(hmac.new(SECRET.encode(), signed, hashlib.sha256).digest())
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if not isinstance(claims, dict):
            raise ValueError("invalid token payload")
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature mismatch")
        if claims.get("iss") != "resilience-auth" or float(claims.get("exp", 0)) <= time.time():
            raise ValueError("expired or invalid issuer")
        with _connect() as connection:
            user = connection.execute(
                "SELECT role, active FROM users WHERE username = ?",
                (claims.get("sub"),),
            ).fetchone()
        if not user or not user["active"] or user["role"] != claims.get("role"):
            raise HTTPException(status_code=401, detail="Account is no longer active")
        return claims
    except HTTPException:
        raise
    except (
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        binascii.Error,
    ) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired operator token") from exc


def _require_admin(authorization: str | None) -> dict:
    claims = _authenticate_request(authorization)
    if claims.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Administrator role required")
    return claims


def _publish_led(state: str) -> None:
    payload = json.dumps({"state": state, "sent_at": int(time.time())})
    try:
        mqtt_publish.single(
            "resilience/led/state",
            payload,
            hostname=MQTT_HOST,
            port=MQTT_PORT,
            qos=1,
            retain=False,
            auth={"username": MQTT_USERNAME, "password": MQTT_PASSWORD},
            timeout=2,
        )
    except (MQTTException, OSError, ValueError) as exc:
        logger.warning("LED controller notification failed for %s: %s", state, exc)


def _face_agent(path: str, *, method: str = "GET", payload: dict | None = None) -> dict:
    try:
        response = requests.request(
            method,
            f"{FACE_AGENT_URL}{path}",
            headers={"X-Face-Agent-Token": FACE_AGENT_TOKEN},
            json=payload,
            timeout=60,
        )
    except requests.RequestException as exc:
        logger.error("Host face agent is unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="Caméra du PC hôte indisponible.") from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", "Face recognition request failed")
        except requests.JSONDecodeError:
            detail = "Face recognition service returned an invalid response."
        raise HTTPException(status_code=response.status_code, detail=detail)
    try:
        payload = response.json()
    except requests.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="Face recognition service returned an invalid response.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="Face recognition service returned an invalid response.")
    return payload


def _face_failure(username: str) -> tuple[int, float]:
    now = time.time()
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT failures, locked_until FROM face_failures WHERE username = ?",
            (username,),
        ).fetchone()
        failures = row["failures"] if row else 0
        locked_until = row["locked_until"] if row else 0
        failures += 1
        if failures >= FACE_FAILURE_LIMIT:
            locked_until = now + FACE_LOCK_SECONDS
            failures = 0
        connection.execute(
            """
            INSERT INTO face_failures (username, failures, locked_until) VALUES (?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET failures=excluded.failures, locked_until=excluded.locked_until
            """,
            (username, failures, locked_until),
        )
    return failures, locked_until


def _valid_password(username: str, password: str) -> sqlite3.Row | None:
    with _connect() as connection:
        user = connection.execute(
            "SELECT username, salt, password_hash, role, active FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if not user or not user["active"]:
        return None
    _, candidate = _hash_password(password, user["salt"])
    return user if hmac.compare_digest(candidate, user["password_hash"]) else None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/face/verify")
def verify_face(request: UsernameRequest):
    username = request.username.strip()
    if not username:
        raise HTTPException(status_code=422, detail="Saisissez un identifiant.")
    with _connect() as connection:
        user = connection.execute(
            "SELECT username, active FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        failure = connection.execute(
            "SELECT failures, locked_until FROM face_failures WHERE username = ?",
            (username,),
        ).fetchone()
    if failure and failure["locked_until"] > time.time():
        remaining = int(failure["locked_until"] - time.time()) + 1
        raise HTTPException(
            status_code=423,
            detail=f"Compte temporairement bloqué. Réessayez dans {remaining} s.",
            headers={"Retry-After": str(remaining)},
        )
    try:
        result = _face_agent("/recognize", method="POST", payload={"username": username})
    except HTTPException as exc:
        if exc.status_code != 422:
            raise
        result = {"recognized": False}
    if not user or not user["active"] or result.get("recognized") is not True:
        _, locked_until = _face_failure(username)
        _publish_led("face_denied")
        if locked_until > time.time():
            raise HTTPException(
                status_code=423,
                detail="Deux échecs de reconnaissance. Accès bloqué pendant 5 minutes.",
                headers={"Retry-After": str(FACE_LOCK_SECONDS)},
            )
        raise HTTPException(
            status_code=401,
            detail="Visage non reconnu. Vérifiez la caméra et réessayez.",
            headers={"Retry-After": "30"},
        )

    challenge_id = secrets.token_urlsafe(32)
    challenges[challenge_id] = (username, time.time() + CHALLENGE_TTL_SECONDS)
    with _connect() as connection:
        connection.execute("DELETE FROM face_failures WHERE username = ?", (username,))
    _publish_led("password_pending")
    return {"challenge_id": challenge_id, "expires_in": CHALLENGE_TTL_SECONDS}


@app.post("/token")
def issue_token(credentials: Credentials):
    challenge = challenges.pop(credentials.challenge_id, None)
    if (
        not challenge
        or challenge[0].casefold() != credentials.username.casefold()
        or challenge[1] <= time.time()
    ):
        _publish_led("off")
        raise HTTPException(status_code=401, detail="Vérification faciale expirée. Recommencez.")

    user = _valid_password(credentials.username, credentials.password)
    if not user:
        _publish_led("password_denied")
        raise HTTPException(status_code=401, detail="Mot de passe incorrect. Recommencez l’identification.")
    _publish_led("granted")
    return _issue_token(user["username"], user["role"])


@app.post("/face/cancel")
def cancel_face_challenge(request: ChallengeRequest):
    challenges.pop(request.challenge_id, None)
    _publish_led("off")
    return {"cancelled": True}


@app.post("/service/token")
def issue_service_token(credentials: ServiceCredentials):
    if credentials.client_id != "aiops-detector" or not hmac.compare_digest(
        credentials.client_secret, AIOPS_CLIENT_SECRET
    ):
        raise HTTPException(status_code=401, detail="Invalid service credentials")
    return _issue_token("aiops-detector", "operator")


@app.get("/admin/users")
def list_users(authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    remote_users = _face_agent("/users").get("users", [])
    enrolled = {username.casefold() for username in remote_users}
    with _connect() as connection:
        users = connection.execute(
            "SELECT username, role, active FROM users ORDER BY username COLLATE NOCASE"
        ).fetchall()
    return {
        "users": [
            {
                "username": user["username"],
                "role": user["role"],
                "active": bool(user["active"]),
                "face_enrolled": user["username"].casefold() in enrolled,
            }
            for user in users
        ]
    }


@app.post("/admin/users", status_code=201)
def create_user(user: UserCreate, authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    salt, digest = _hash_password(user.password)
    try:
        with _connect() as connection:
            connection.execute(
                "INSERT INTO users (username, salt, password_hash, role) VALUES (?, ?, ?, ?)",
                (user.username, salt, digest, user.role),
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Cet identifiant existe déjà.") from exc
    return {"username": user.username, "role": user.role, "active": True, "face_enrolled": False}


@app.post("/admin/users/{username}/face")
def enroll_face(username: str, authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    with _connect() as connection:
        user = connection.execute(
            "SELECT username, active FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if not user or not user["active"]:
        raise HTTPException(status_code=404, detail="Utilisateur inconnu ou désactivé.")
    result = _face_agent("/users/enroll", method="POST", payload={"username": username})
    return {"username": username, "face_enrolled": True, "samples": result.get("samples")}


@app.delete("/admin/users/{username}")
def delete_user(username: str, authorization: str | None = Header(default=None)):
    claims = _require_admin(authorization)
    with _connect() as connection:
        user = connection.execute("SELECT role FROM users WHERE username = ?", (username,)).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Utilisateur inconnu.")
        if claims.get("sub", "").casefold() == username.casefold():
            raise HTTPException(status_code=400, detail="Vous ne pouvez pas supprimer votre propre compte.")
        if user["role"] == "admin":
            other_admin = connection.execute(
                "SELECT 1 FROM users WHERE role = 'admin' AND active = 1 AND username != ?",
                (username,),
            ).fetchone()
            if not other_admin:
                raise HTTPException(status_code=400, detail="Le dernier administrateur ne peut pas être supprimé.")
        _face_agent(f"/users/{quote(username, safe='')}", method="DELETE")
        connection.execute("DELETE FROM users WHERE username = ?", (username,))
        connection.execute("DELETE FROM face_failures WHERE username = ?", (username,))
    return {"deleted": username}

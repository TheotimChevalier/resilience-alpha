import hmac
import io
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from cryptography.fernet import Fernet, InvalidToken
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from face_agent.led_serial import LedSerialBridge
from face_agent.recognition import (
    FACE_SIMILARITY_THRESHOLD as DEFAULT_FACE_SIMILARITY_THRESHOLD,
    cosine_similarity,
    face_embedding,
    load_face_models,
)

TOKEN = os.getenv("FACE_AGENT_TOKEN", "")
DATA_KEY = os.getenv("FACE_DATA_KEY", "")
DB_PATH = Path(os.getenv("FACE_DB_PATH", "face_agent/data/faces.sqlite3"))
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))
ESP_SERIAL_PORT = os.getenv("ESP_SERIAL_PORT", "COM3")
ESP_SERIAL_BAUD = int(os.getenv("ESP_SERIAL_BAUD", "115200"))
CAMERA_BACKEND = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
FACE_SIMILARITY_THRESHOLD = float(
    os.getenv(
        "FACE_SIMILARITY_THRESHOLD",
        str(DEFAULT_FACE_SIMILARITY_THRESHOLD),
    )
)
if not 0 < FACE_SIMILARITY_THRESHOLD <= 1:
    raise RuntimeError("FACE_SIMILARITY_THRESHOLD must be between 0 and 1")
CAMERA_TIMEOUT_SECONDS = float(os.getenv("CAMERA_TIMEOUT_SECONDS", "12"))
SAMPLE_COUNT = 8
RECOGNITION_SAMPLE_COUNT = 5
camera_lock = threading.Lock()
if len(TOKEN) < 32:
    raise RuntimeError("FACE_AGENT_TOKEN must contain at least 32 characters")
try:
    cipher = Fernet(DATA_KEY.encode())
except (ValueError, TypeError) as exc:
    raise RuntimeError("FACE_DATA_KEY must be a valid Fernet key") from exc

app = FastAPI(title="Resilience Alpha Host Face Agent", version="1.0.0")
logger = logging.getLogger("face_agent")
led_serial = LedSerialBridge(ESP_SERIAL_PORT, baudrate=ESP_SERIAL_BAUD)


class UserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)


class LedStateRequest(BaseModel):
    state: Literal[
        "off",
        "password_pending",
        "face_denied",
        "password_denied",
        "granted",
        "hardware_test",
    ]


@contextmanager
def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _require_agent_token(token: str | None) -> None:
    if not token or not hmac.compare_digest(token, TOKEN):
        raise HTTPException(status_code=403, detail="Face agent credential required")


def _extract_face(frame: np.ndarray) -> np.ndarray | None:
    try:
        detector, recognizer = load_face_models()
        return face_embedding(frame, detector, recognizer)
    except ValueError:
        return None


def _capture_samples(count: int, timeout: float = CAMERA_TIMEOUT_SECONDS) -> list[np.ndarray]:
    if not camera_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="La caméra est déjà utilisée.")
    camera = None
    try:
        camera = cv2.VideoCapture(CAMERA_INDEX, CAMERA_BACKEND)
        if not camera.isOpened():
            raise HTTPException(
                status_code=503,
                detail=f"Caméra USB hôte introuvable (index {CAMERA_INDEX}).",
            )
        deadline = time.monotonic() + timeout
        samples: list[np.ndarray] = []
        while time.monotonic() < deadline and len(samples) < count:
            ok, frame = camera.read()
            if not ok:
                time.sleep(0.1)
                continue
            face = _extract_face(frame)
            if face is not None:
                samples.append(face)
                time.sleep(0.2)
        if not samples:
            raise HTTPException(status_code=422, detail="Aucun visage unique détecté par la caméra.")
        if count > 1 and len(samples) < count:
            raise HTTPException(
                status_code=422,
                detail=f"Enrôlement incomplet : {len(samples)}/{count} images valides.",
            )
        return samples
    finally:
        if camera is not None:
            camera.release()
        camera_lock.release()


def _read_samples(username: str) -> list[np.ndarray]:
    with _connect() as connection:
        row = connection.execute(
            "SELECT samples FROM face_profiles WHERE username = ?",
            (username,),
        ).fetchone()
    if not row:
        return []
    try:
        archive = np.load(io.BytesIO(cipher.decrypt(row["samples"])), allow_pickle=False)
        detector, recognizer = load_face_models()
        samples = []
        for key in sorted(archive.files):
            sample = archive[key]
            if sample.ndim == 2:
                sample = face_embedding(sample, detector, recognizer)
            elif sample.ndim != 1 or sample.shape != (128,):
                raise ValueError("Unsupported face profile sample format")
            if not np.isfinite(sample).all():
                raise ValueError("Face profile contains a non-finite embedding")
            samples.append(sample.astype(np.float32))
        return samples
    except (InvalidToken, ValueError, OSError) as exc:
        raise RuntimeError(f"Encrypted face profile for {username!r} cannot be read") from exc


def _store_samples(username: str, samples: list[np.ndarray]) -> None:
    if not samples or any(sample.shape != (128,) for sample in samples):
        raise ValueError("Face profiles must contain one or more face embeddings.")
    output = io.BytesIO()
    np.savez_compressed(output, **{f"sample_{index:03d}": image for index, image in enumerate(samples)})
    encrypted = cipher.encrypt(output.getvalue())
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO face_profiles (username, samples) VALUES (?, ?)
            ON CONFLICT(username) DO UPDATE SET samples=excluded.samples
            """,
            (username, encrypted),
        )


def _all_profiles() -> dict[str, list[np.ndarray]]:
    with _connect() as connection:
        usernames = [
            row["username"]
            for row in connection.execute(
                "SELECT username FROM face_profiles ORDER BY username COLLATE NOCASE"
            )
        ]
    return {username: _read_samples(username) for username in usernames}


with _connect() as connection:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS face_profiles (
            username TEXT PRIMARY KEY COLLATE NOCASE,
            samples BLOB NOT NULL
        )
        """
    )


@app.get("/health")
def health():
    return {"status": "ok", "camera_index": CAMERA_INDEX}


@app.post("/led/state")
def set_led_state(request: LedStateRequest, x_face_agent_token: str | None = Header(default=None)):
    _require_agent_token(x_face_agent_token)
    try:
        led_serial.send(request.state)
    except (OSError, UnicodeDecodeError) as exc:
        logger.error(
            "ESP8266 serial notification failed for %s on %s: %s",
            request.state,
            ESP_SERIAL_PORT,
            exc,
        )
        raise HTTPException(status_code=503, detail="Contrôleur LED ESP8266 indisponible sur le port série.") from exc
    return {"state": request.state, "status": "sent"}


@app.get("/users")
def list_users(x_face_agent_token: str | None = Header(default=None)):
    _require_agent_token(x_face_agent_token)
    with _connect() as connection:
        users = [
            row["username"]
            for row in connection.execute(
                "SELECT username FROM face_profiles ORDER BY username COLLATE NOCASE"
            )
        ]
    return {"users": users}


@app.post("/recognize")
def recognize(user: UserRequest, x_face_agent_token: str | None = Header(default=None)):
    _require_agent_token(x_face_agent_token)
    try:
        load_face_models()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    profiles = _all_profiles()
    samples = _capture_samples(count=RECOGNITION_SAMPLE_COUNT)
    if not profiles:
        return {"recognized": False}
    requested_samples = next(
        (
            user_samples
            for username, user_samples in profiles.items()
            if hmac.compare_digest(username.casefold(), user.username.casefold())
        ),
        None,
    )
    if not requested_samples:
        return {"recognized": False, "confidence_similarity": None, "samples": len(samples)}

    similarities = []
    recognized_samples = 0
    for sample in samples:
        similarity = max(
            cosine_similarity(sample, reference)
            for reference in requested_samples
        )
        similarities.append(similarity)
        if similarity >= FACE_SIMILARITY_THRESHOLD:
            recognized_samples += 1
    required_samples = (len(samples) + 1) // 2
    confidence_similarity = (
        round(float(np.median(similarities)), 4) if similarities else None
    )
    matched = recognized_samples >= required_samples
    return {
        "recognized": matched,
        "confidence_similarity": confidence_similarity,
        "samples": len(samples),
        "recognized_samples": recognized_samples,
        "required_samples": required_samples,
    }


@app.post("/users/enroll", status_code=201)
def enroll(user: UserRequest, x_face_agent_token: str | None = Header(default=None)):
    _require_agent_token(x_face_agent_token)
    try:
        load_face_models()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    samples = _capture_samples(count=SAMPLE_COUNT, timeout=CAMERA_TIMEOUT_SECONDS * 4)
    _store_samples(user.username, samples)
    return {"username": user.username, "samples": len(samples)}


@app.delete("/users/{username}")
def delete_user(username: str, x_face_agent_token: str | None = Header(default=None)):
    _require_agent_token(x_face_agent_token)
    with _connect() as connection:
        cursor = connection.execute("DELETE FROM face_profiles WHERE username = ?", (username,))
    return {"deleted": username, "face_profile_removed": cursor.rowcount > 0}


def run() -> None:
    import uvicorn

    uvicorn.run(app, host=os.getenv("FACE_AGENT_BIND", "0.0.0.0"), port=int(os.getenv("FACE_AGENT_PORT", "8765")))


if __name__ == "__main__":
    run()

import hmac
import io
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import cv2
import numpy as np
from cryptography.fernet import Fernet, InvalidToken
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

TOKEN = os.getenv("FACE_AGENT_TOKEN", "")
DATA_KEY = os.getenv("FACE_DATA_KEY", "")
DB_PATH = Path(os.getenv("FACE_DB_PATH", "face_agent/data/faces.sqlite3"))
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))
CAMERA_BACKEND = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
FACE_SIZE = (128, 128)
FACE_DISTANCE_THRESHOLD = float(os.getenv("FACE_DISTANCE_THRESHOLD", "55"))
CAMERA_TIMEOUT_SECONDS = float(os.getenv("CAMERA_TIMEOUT_SECONDS", "12"))
SAMPLE_COUNT = 8
camera_lock = threading.Lock()
FACE_CASCADE = cv2.CascadeClassifier(
    str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
)
if FACE_CASCADE.empty():
    raise RuntimeError("OpenCV Haar face-detection model is unavailable")

if len(TOKEN) < 32:
    raise RuntimeError("FACE_AGENT_TOKEN must contain at least 32 characters")
try:
    cipher = Fernet(DATA_KEY.encode())
except (ValueError, TypeError) as exc:
    raise RuntimeError("FACE_DATA_KEY must be a valid Fernet key") from exc

app = FastAPI(title="Resilience Alpha Host Face Agent", version="1.0.0")


class UserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)


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
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = FACE_CASCADE.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(80, 80),
    )
    if len(faces) != 1:
        return None
    x, y, width, height = faces[0]
    return cv2.resize(gray[y : y + height, x : x + width], FACE_SIZE)
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
        return [archive[key] for key in sorted(archive.files)]
    except (InvalidToken, ValueError, OSError) as exc:
        raise RuntimeError(f"Encrypted face profile for {username!r} cannot be read") from exc


def _store_samples(username: str, samples: list[np.ndarray]) -> None:
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
    profiles = _all_profiles()
    samples = _capture_samples(count=1)
    if not profiles:
        return {"recognized": False}
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    labels: list[str] = []
    training_images: list[np.ndarray] = []
    for username, user_samples in profiles.items():
        labels.append(username)
        training_images.extend(user_samples)
    training_labels = np.concatenate(
        [np.full(len(profile_samples), label, dtype=np.int32)
         for label, profile_samples in enumerate(profiles.values())]
    )
    recognizer.train(training_images, training_labels)
    predicted_label, distance = recognizer.predict(samples[0])
    matched = (
        0 <= predicted_label < len(labels)
        and hmac.compare_digest(labels[predicted_label].casefold(), user.username.casefold())
        and distance <= FACE_DISTANCE_THRESHOLD
    )
    return {"recognized": bool(matched), "confidence_distance": round(float(distance), 2)}


@app.post("/users/enroll", status_code=201)
def enroll(user: UserRequest, x_face_agent_token: str | None = Header(default=None)):
    _require_agent_token(x_face_agent_token)
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

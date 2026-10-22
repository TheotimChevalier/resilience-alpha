import threading
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

MODEL_DIR = Path(__file__).resolve().parent / "models"
DETECTOR_MODEL = MODEL_DIR / "face_detection_yunet_2023mar.onnx"
RECOGNIZER_MODEL = MODEL_DIR / "face_recognition_sface_2021dec.onnx"
FACE_SIMILARITY_THRESHOLD = 0.363
_model_lock = threading.Lock()


@lru_cache(maxsize=1)
def load_face_models():
    missing = [
        model.name
        for model in (DETECTOR_MODEL, RECOGNIZER_MODEL)
        if not model.is_file()
    ]
    if missing:
        raise RuntimeError(
            "Face models are missing: "
            + ", ".join(missing)
            + ". Run `py -3.12 -m face_agent.download_models`."
        )
    try:
        detector = cv2.FaceDetectorYN_create(
            str(DETECTOR_MODEL),
            "",
            (320, 320),
            0.8,
            0.3,
            5000,
        )
        recognizer = cv2.FaceRecognizerSF_create(str(RECOGNIZER_MODEL), "")
    except cv2.error as exc:
        raise RuntimeError(f"OpenCV could not load the local face models: {exc}") from exc
    return detector, recognizer


def face_embedding(
    image: np.ndarray,
    detector=None,
    recognizer=None,
) -> np.ndarray:
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("Expected a grayscale or BGR image.")

    if detector is None or recognizer is None:
        detector, recognizer = load_face_models()

    with _model_lock:
        detector.setInputSize((image.shape[1], image.shape[0]))
        _, faces = detector.detect(image)
        if faces is None or len(faces) != 1:
            face_count = 0 if faces is None else len(faces)
            raise ValueError(f"Expected exactly one face, found {face_count}.")
        aligned_face = recognizer.alignCrop(image, faces[0])
        embedding = recognizer.feature(aligned_face).reshape(-1).astype(np.float32)

    norm = float(np.linalg.norm(embedding))
    if norm == 0 or not np.isfinite(norm):
        raise ValueError("OpenCV produced an invalid face embedding.")
    return embedding / norm


def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_vector = np.asarray(left, dtype=np.float32).reshape(-1)
    right_vector = np.asarray(right, dtype=np.float32).reshape(-1)
    if left_vector.shape != right_vector.shape:
        raise ValueError("Face embeddings have incompatible dimensions.")
    return float(np.dot(left_vector, right_vector))

import argparse
import statistics
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from face_agent.led_serial import LedSerialBridge
from face_agent.recognition import (
    FACE_SIMILARITY_THRESHOLD,
    cosine_similarity,
    face_embedding,
    load_face_models,
)

IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


class NoLiveFaceError(RuntimeError):
    pass


def _send_led_state(port: str, state: str) -> None:
    bridge = LedSerialBridge(port)
    try:
        bridge.send(state)
    finally:
        bridge.close()
    print(f"ESP8266 LED: {state} on {port}.")


def find_reference_images(path: Path) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            raise ValueError(f"Unsupported image format: {path.suffix}")
        return [path]
    if path.is_dir():
        return sorted(
            (
                candidate
                for candidate in path.iterdir()
                if candidate.is_file() and candidate.suffix.lower() in IMAGE_SUFFIXES
            ),
            key=lambda candidate: candidate.name.casefold(),
        )
    raise ValueError(f"Reference image or folder does not exist: {path}")


def load_reference_faces(
    path: Path,
    embedding_function=face_embedding,
    models=None,
) -> tuple[list[np.ndarray], list[Path]]:
    image_paths = find_reference_images(path)
    if not image_paths:
        raise ValueError(f"No supported images found in folder: {path}")
    if models is None:
        models = load_face_models()
    faces: list[np.ndarray] = []
    for image_path in image_paths:
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"OpenCV could not read reference image: {image_path}")
        try:
            faces.append(embedding_function(image, *models))
        except ValueError as exc:
            raise ValueError(f"Invalid reference image {image_path.name}: {exc}") from exc
    return faces, image_paths


def compare_faces(
    reference_embeddings: list[np.ndarray],
    live_embeddings: list[np.ndarray],
) -> list[float]:
    if not reference_embeddings:
        raise ValueError("No reference face images were loaded.")
    if not live_embeddings:
        raise ValueError("No live camera face samples were collected.")
    return [
        max(cosine_similarity(live, reference) for reference in reference_embeddings)
        for live in live_embeddings
    ]


def decide_match(
    similarities: list[float],
    threshold: float,
) -> tuple[bool, int, float | None]:
    if not similarities:
        raise ValueError("No live camera face samples were collected.")
    accepted_samples = sum(similarity >= threshold for similarity in similarities)
    required_samples = (len(similarities) + 1) // 2
    return (
        accepted_samples >= required_samples,
        accepted_samples,
        float(statistics.median(similarities)),
    )


def capture_live_faces(
    camera_index: int,
    models,
    sample_count: int,
    timeout: float,
) -> list[np.ndarray]:
    camera = cv2.VideoCapture(
        camera_index,
        cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY,
    )
    if not camera.isOpened():
        camera.release()
        raise RuntimeError(f"Camera index {camera_index} could not be opened.")

    deadline = time.monotonic() + timeout
    samples: list[np.ndarray] = []
    errors: dict[str, int] = {}
    try:
        while time.monotonic() < deadline and len(samples) < sample_count:
            ok, frame = camera.read()
            if not ok:
                errors["camera frame unavailable"] = errors.get("camera frame unavailable", 0) + 1
                time.sleep(0.1)
                continue
            try:
                samples.append(face_embedding(frame, *models))
            except ValueError as exc:
                reason = str(exc)
                errors[reason] = errors.get(reason, 0) + 1
            time.sleep(0.2)
    finally:
        camera.release()

    if not samples:
        detail = ", ".join(f"{reason}: {count}" for reason, count in errors.items())
        raise NoLiveFaceError(
            f"No face was captured before timeout ({detail or 'no camera frames'})."
        )
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare a local SFace reference gallery with live webcam frames."
    )
    parser.add_argument(
        "image",
        type=Path,
        nargs="?",
        default=Path(__file__).resolve().parents[1] / "photo",
        help="Reference image or folder of images (default: the project's photo folder)",
    )
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default: 0)")
    parser.add_argument(
        "--threshold",
        type=float,
        default=FACE_SIMILARITY_THRESHOLD,
        help="Cosine similarity threshold between 0 and 1 (default: 0.363)",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=8,
        help="Number of live face frames to compare (default: 8)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30,
        help="Seconds allowed to collect samples (default: 30)",
    )
    parser.add_argument(
        "--led",
        action="store_true",
        help="Allume la LED verte si le visage est reconnu, rouge sinon.",
    )
    parser.add_argument(
        "--led-on-mismatch",
        action="store_true",
        help="Send the red face_denied alert to the ESP8266 if the image does not match.",
    )
    parser.add_argument("--serial-port", default="COM3", help="ESP8266 serial port (default: COM3)")
    args = parser.parse_args()

    if args.samples < 1 or args.samples > 100:
        parser.error("--samples must be between 1 and 100")
    if args.timeout <= 0 or not 0 < args.threshold <= 1:
        parser.error("--timeout must be positive and --threshold must be between 0 and 1")

    models = load_face_models()
    reference_embeddings, reference_paths = load_reference_faces(args.image, models=models)
    print(f"Knowledge base: {len(reference_embeddings)} local reference images")
    for reference_path in reference_paths:
        print(f"  - {reference_path.name}")
    print("Place the person in front of the host webcam. Captures stay on this PC.")

    try:
        live_embeddings = capture_live_faces(args.camera, models, args.samples, args.timeout)
    except NoLiveFaceError as exc:
        print(str(exc), file=sys.stderr)
        print("Result: NO MATCH (no live face available)")
        if args.led or args.led_on_mismatch:
            _send_led_state(args.serial_port, "face_denied")
        return 1

    similarities = compare_faces(reference_embeddings, live_embeddings)
    match, accepted_samples, median_similarity = decide_match(
        similarities,
        threshold=args.threshold,
    )

    print(
        f"Live samples: {len(similarities)}/{args.samples}; "
        f"SFace median cosine similarity={median_similarity:.4f}, "
        f"min={min(similarities):.4f}, accepted={accepted_samples}/{len(live_embeddings)} "
        f"(majority required), threshold={args.threshold:.4f}"
    )
    print(f"Result: {'MATCH' if match else 'NO MATCH'}")
    print("This local prototype does not verify liveness or prove identity.")

    if args.led and match:
        _send_led_state(args.serial_port, "granted")
    elif (args.led or args.led_on_mismatch) and not match:
        _send_led_state(args.serial_port, "face_denied")

    return 0 if match else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError, cv2.error) as exc:
        print(f"Face comparison failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

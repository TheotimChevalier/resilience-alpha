import hashlib
import os
import tempfile
from pathlib import Path
from urllib.request import urlopen

MODEL_REVISION = "48b10fa505aeb51fbd127fc60a5c660040e823b7"
MODEL_DIR = Path(__file__).resolve().parent / "models"
MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        "models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    "face_recognition_sface_2021dec.onnx": (
        "models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
}


def _download_model(name: str, relative_path: str, expected_sha256: str) -> None:
    url = (
        "https://github.com/opencv/opencv_zoo/raw/"
        f"{MODEL_REVISION}/{relative_path}"
    )
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    destination = MODEL_DIR / name
    with tempfile.NamedTemporaryFile(dir=MODEL_DIR, delete=False) as temporary:
        temporary_path = Path(temporary.name)
        try:
            with urlopen(url, timeout=60) as response:
                digest = hashlib.sha256()
                while chunk := response.read(1024 * 1024):
                    temporary.write(chunk)
                    digest.update(chunk)
        except OSError:
            temporary_path.unlink(missing_ok=True)
            raise
    if digest.hexdigest() != expected_sha256:
        temporary_path.unlink(missing_ok=True)
        raise RuntimeError(f"SHA-256 verification failed for {name}.")
    os.replace(temporary_path, destination)
    print(f"Installed {name} ({destination.stat().st_size:,} bytes).")


def main() -> None:
    for name, (relative_path, checksum) in MODELS.items():
        _download_model(name, relative_path, checksum)
    print("Models downloaded from OpenCV Zoo and verified by SHA-256.")


if __name__ == "__main__":
    main()

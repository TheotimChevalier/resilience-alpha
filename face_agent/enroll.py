import argparse
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enroll a user from the host camera or import local reference images."
    )
    parser.add_argument("username", help="Existing back-office account username")
    parser.add_argument(
        "--images",
        type=Path,
        help="Import every supported image in a local folder instead of capturing from the camera.",
    )
    args = parser.parse_args()
    if args.images:
        from face_agent.main import _store_samples
        from face_agent.recognition import face_embedding, load_face_models
        from face_agent.test_live_match import load_reference_faces

        reference_faces, image_paths = load_reference_faces(
            args.images, face_embedding, load_face_models()
        )
        _store_samples(args.username, reference_faces)
        print(
            f"Imported {len(reference_faces)} encrypted face references for "
            f"{args.username} from {args.images.resolve()}."
        )
        print("Files: " + ", ".join(path.name for path in image_paths))
        return

    base_url = os.getenv("FACE_AGENT_URL_LOCAL", "http://127.0.0.1:8765").rstrip("/")
    token = os.getenv("FACE_AGENT_TOKEN")
    if not token:
        parser.error("FACE_AGENT_TOKEN must be set in the host environment or .env file")
    response = requests.post(
        f"{base_url}/users/enroll",
        headers={"X-Face-Agent-Token": token},
        json={"username": args.username},
        timeout=60,
    )
    response.raise_for_status()
    print(f"Face enrollment complete for {args.username}: {response.json()['samples']} samples.")


if __name__ == "__main__":
    main()

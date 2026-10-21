import argparse
import os

import requests
from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture initial face enrollment on the PC hosting the USB camera."
    )
    parser.add_argument("username", help="Existing back-office account username")
    args = parser.parse_args()
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

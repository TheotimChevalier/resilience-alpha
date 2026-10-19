"""Create a source archive without local secrets, dependencies, or build outputs."""

import argparse
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDED = (
    ".env.example",
    ".gitignore",
    "README.md",
    "docker-compose.yml",
    "prometheus.yml",
    "loki-config.yml",
    "api",
    "auth",
    "aiops",
    "ansible",
    "dashboard",
    "docs",
    "observability",
    "rag",
    "redteam",
    "scripts",
)
EXCLUDED_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "dist",
    "node_modules",
    "venv",
    "env",
    "secrets",
}
EXCLUDED_NAMES = {".env", ".env.local", ".env.production", "key.txt"}
EXCLUDED_SUFFIXES = {".enc", ".key", ".pem", ".pyc", ".zip", ".mp4", ".db", ".sqlite"}


def is_safe(path: Path) -> bool:
    if not path.resolve().is_relative_to(ROOT):
        return False
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        return False
    if path.name in EXCLUDED_NAMES or path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if path.name.startswith(".env.") and path.name != ".env.example":
        return False
    return path.is_file()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team", required=True, help="Team number used in the required archive name")
    parser.add_argument("--output", type=Path, help="Optional output path")
    args = parser.parse_args()
    if not re.fullmatch(r"\d{1,3}", args.team):
        parser.error("--team must be a one-to-three digit team number")

    destination = args.output or ROOT / f"Workshop2026-M2-G{args.team}-Code.zip"
    destination = destination.resolve()
    files = []
    for entry in INCLUDED:
        path = ROOT / entry
        if path.is_file() and is_safe(path):
            files.append(path)
        elif path.is_dir():
            files.extend(file for file in path.rglob("*") if is_safe(file))

    if not files:
        raise RuntimeError("No source files were selected for the archive")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(set(files)):
            archive.write(file, file.relative_to(ROOT).as_posix())

    with zipfile.ZipFile(destination) as archive:
        unsafe = [
            name
            for name in archive.namelist()
            if any(part in EXCLUDED_DIRS for part in Path(name).parts)
            or Path(name).name in EXCLUDED_NAMES
            or Path(name).suffix.lower() in EXCLUDED_SUFFIXES
            or (Path(name).name.startswith(".env.") and Path(name).name != ".env.example")
        ]
        if unsafe:
            destination.unlink(missing_ok=True)
            raise RuntimeError(f"Unsafe files found in archive: {unsafe}")
    print(f"Created {destination} with {len(files)} source files.")


if __name__ == "__main__":
    main()

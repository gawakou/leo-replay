from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable


MANIFEST_NAME = "evaluation-manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def iter_artifacts(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == MANIFEST_NAME:
            continue
        yield path


def create_evaluation_manifest(root: Path) -> dict[str, object]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"evaluation directory does not exist: {root}")

    files = []
    for path in iter_artifacts(root):
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )

    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "kind": "leo-replay-evaluation-artifacts",
        "files": files,
    }
    (root / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def verify_evaluation_manifest(root: Path) -> list[str]:
    root = root.resolve()
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.exists():
        return [f"{MANIFEST_NAME} is missing"]

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read {MANIFEST_NAME}: {exc}"]

    entries = manifest.get("files")
    if not isinstance(entries, list):
        return ["manifest files must be a list"]

    errors: list[str] = []
    expected_paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("invalid file entry in manifest")
            continue
        relative = entry.get("path")
        expected_hash = entry.get("sha256")
        expected_size = entry.get("size_bytes")
        if not isinstance(relative, str) or not isinstance(expected_hash, str):
            errors.append("manifest file entry is missing path or sha256")
            continue
        expected_paths.add(relative)
        path = root / relative
        if not path.is_file():
            errors.append(f"missing file: {relative}")
            continue
        if isinstance(expected_size, int) and path.stat().st_size != expected_size:
            errors.append(f"size mismatch: {relative}")
        if sha256_file(path) != expected_hash:
            errors.append(f"sha256 mismatch: {relative}")

    actual_paths = {path.relative_to(root).as_posix() for path in iter_artifacts(root)}
    for relative in sorted(actual_paths - expected_paths):
        errors.append(f"untracked file: {relative}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create or verify a LEO-Replay evaluation artifact manifest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="create a deterministic SHA-256 manifest")
    create_parser.add_argument("directory", type=Path)

    verify_parser = subparsers.add_parser("verify", help="verify files against the saved manifest")
    verify_parser.add_argument("directory", type=Path)

    args = parser.parse_args(argv)
    if args.command == "create":
        manifest = create_evaluation_manifest(args.directory)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0

    errors = verify_evaluation_manifest(args.directory)
    if errors:
        for error in errors:
            print(error)
        return 1
    print("evaluation manifest verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

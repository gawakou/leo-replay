from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Iterable


MANIFEST_NAME = "evaluation-manifest.json"
SCHEMA_VERSION = "1.0"
MANIFEST_KIND = "leo-replay-evaluation-artifacts"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def iter_artifacts(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.name == MANIFEST_NAME:
            continue
        if path.is_symlink() or path.is_file():
            yield path


def create_evaluation_manifest(root: Path) -> dict[str, object]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"evaluation directory does not exist: {root}")

    manifest_path = root / MANIFEST_NAME
    if manifest_path.is_symlink():
        raise ValueError(f"{MANIFEST_NAME} must not be a symbolic link")

    files = []
    for path in iter_artifacts(root):
        if path.is_symlink():
            raise ValueError(f"evaluation artifacts must not be symbolic links: {path.relative_to(root).as_posix()}")
        files.append({"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path), "size_bytes": path.stat().st_size})

    manifest: dict[str, object] = {"schema_version": SCHEMA_VERSION, "kind": MANIFEST_KIND, "files": files}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def _safe_manifest_path(relative: str) -> bool:
    if not relative or "\\" in relative:
        return False
    path = PurePosixPath(relative)
    return not path.is_absolute() and path.as_posix() == relative and ".." not in path.parts and "." not in path.parts


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def verify_evaluation_manifest(root: Path) -> list[str]:
    root = root.resolve()
    manifest_path = root / MANIFEST_NAME
    if manifest_path.is_symlink():
        return [f"{MANIFEST_NAME} must not be a symbolic link"]
    if not manifest_path.exists():
        return [f"{MANIFEST_NAME} is missing"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read {MANIFEST_NAME}: {exc}"]

    errors: list[str] = []
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"unsupported manifest schema_version: {manifest.get('schema_version')!r}")
    if manifest.get("kind") != MANIFEST_KIND:
        errors.append(f"unexpected manifest kind: {manifest.get('kind')!r}")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        errors.append("manifest files must be a list")
        return errors

    expected_paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("invalid file entry in manifest")
            continue
        relative = entry.get("path")
        expected_hash = entry.get("sha256")
        expected_size = entry.get("size_bytes")
        if not isinstance(relative, str):
            errors.append("manifest file entry is missing path")
            continue
        if not _safe_manifest_path(relative):
            errors.append(f"unsafe manifest path: {relative}")
            continue
        if relative in expected_paths:
            errors.append(f"duplicate manifest path: {relative}")
            continue
        expected_paths.add(relative)
        metadata_valid = True
        if not isinstance(expected_hash, str) or not _valid_sha256(expected_hash):
            errors.append(f"invalid sha256: {relative}")
            metadata_valid = False
        if not isinstance(expected_size, int) or isinstance(expected_size, bool) or expected_size < 0:
            errors.append(f"invalid size_bytes: {relative}")
            metadata_valid = False
        if not metadata_valid:
            continue

        path = root / relative
        if path.is_symlink():
            errors.append(f"symbolic link artifact is not allowed: {relative}")
            continue
        if not path.is_file():
            errors.append(f"missing file: {relative}")
            continue
        if path.stat().st_size != expected_size:
            errors.append(f"size mismatch: {relative}")
        if sha256_file(path) != expected_hash:
            errors.append(f"sha256 mismatch: {relative}")

    actual_paths = {path.relative_to(root).as_posix() for path in iter_artifacts(root)}
    for relative in sorted(actual_paths - expected_paths):
        path = root / relative
        if path.is_symlink():
            errors.append(f"symbolic link artifact is not allowed: {relative}")
        else:
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

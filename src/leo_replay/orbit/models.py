from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json


class OrbitDataError(ValueError):
    """Raised when orbit-related input is invalid."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise OrbitDataError(f"invalid ISO-8601 timestamp: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class ObserverSite:
    site_id: str
    name: str
    latitude_deg: float
    longitude_deg: float
    elevation_m: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.site_id.strip():
            raise OrbitDataError("observer site_id must not be empty")
        if not self.name.strip():
            raise OrbitDataError("observer name must not be empty")
        if not -90.0 <= self.latitude_deg <= 90.0:
            raise OrbitDataError("observer latitude_deg must be between -90 and 90")
        if not -180.0 <= self.longitude_deg <= 180.0:
            raise OrbitDataError("observer longitude_deg must be between -180 and 180")
        if not -500.0 <= self.elevation_m <= 10000.0:
            raise OrbitDataError("observer elevation_m is outside the supported range")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ObserverSite":
        try:
            site = cls(
                site_id=str(value["site_id"]),
                name=str(value["name"]),
                latitude_deg=float(value["latitude_deg"]),
                longitude_deg=float(value["longitude_deg"]),
                elevation_m=float(value.get("elevation_m", 0.0)),
                metadata=dict(value.get("metadata") or {}),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise OrbitDataError(f"invalid observer site document: {exc}") from exc
        site.validate()
        return site

    @classmethod
    def load(cls, path: Path) -> "ObserverSite":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise OrbitDataError(f"invalid observer site JSON: {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise OrbitDataError("observer site document must be a JSON object")
        return cls.from_dict(value)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

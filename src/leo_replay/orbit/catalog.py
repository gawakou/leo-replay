from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from skyfield.api import EarthSatellite, load
from skyfield.iokit import parse_tle_file

from .models import OrbitDataError, iso_utc


@dataclass(frozen=True)
class OrbitSatellite:
    satellite: EarthSatellite
    name: str
    norad_cat_id: str
    object_id: str | None
    epoch_utc: str
    source_fields: dict[str, Any]


@dataclass(frozen=True)
class OrbitCatalog:
    source_path: Path
    source_format: str
    satellites: tuple[OrbitSatellite, ...]

    def select(self, selectors: Iterable[str] | None) -> "OrbitCatalog":
        requested = [item.strip().lower() for item in (selectors or []) if item.strip()]
        if not requested:
            return self
        selected = []
        for record in self.satellites:
            values = {
                record.name.lower(),
                record.norad_cat_id.lower(),
                (record.object_id or "").lower(),
            }
            if any(selector in values or selector in record.name.lower() for selector in requested):
                selected.append(record)
        if not selected:
            raise OrbitDataError(f"no satellites matched selectors: {', '.join(requested)}")
        return OrbitCatalog(self.source_path, self.source_format, tuple(selected))


def timescale():
    # Built-in leap-second data keeps offline tests and replay workflows reproducible.
    return load.timescale(builtin=True)


def detect_orbit_format(path: Path, requested: str = "auto") -> str:
    if requested != "auto":
        return requested
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "omm-json"
    if suffix == ".csv":
        return "omm-csv"
    if suffix in {".tle", ".3le", ".2le"}:
        return "tle"
    prefix = path.read_text(encoding="utf-8", errors="ignore")[:512].lstrip()
    if prefix.startswith("[") or prefix.startswith("{"):
        return "omm-json"
    if "OBJECT_NAME" in prefix and "," in prefix:
        return "omm-csv"
    if prefix.startswith("1 ") or "\n1 " in prefix:
        return "tle"
    raise OrbitDataError(f"could not detect orbit format for {path}")


def _record_from_omm(fields: dict[str, Any], ts) -> OrbitSatellite:
    try:
        satellite = EarthSatellite.from_omm(ts, fields)
    except Exception as exc:  # Skyfield/sgp4 emits several input-specific exception types.
        name = fields.get("OBJECT_NAME", "unnamed")
        raise OrbitDataError(f"failed to parse OMM record {name!r}: {exc}") from exc
    name = str(fields.get("OBJECT_NAME") or satellite.name or f"NORAD-{satellite.model.satnum}")
    cat_id = str(fields.get("NORAD_CAT_ID") or satellite.model.satnum)
    object_id = fields.get("OBJECT_ID")
    return OrbitSatellite(
        satellite=satellite,
        name=name,
        norad_cat_id=cat_id,
        object_id=str(object_id) if object_id not in (None, "") else None,
        epoch_utc=iso_utc(satellite.epoch.utc_datetime()),
        source_fields=dict(fields),
    )


def _load_omm_json(path: Path, ts) -> tuple[OrbitSatellite, ...]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OrbitDataError(f"invalid OMM JSON: {path}: {exc}") from exc
    if isinstance(value, dict):
        if isinstance(value.get("data"), list):
            rows = value["data"]
        else:
            rows = [value]
    elif isinstance(value, list):
        rows = value
    else:
        raise OrbitDataError("OMM JSON must be an object or an array of objects")
    if not rows:
        raise OrbitDataError("OMM JSON contains no satellite records")
    if not all(isinstance(row, dict) for row in rows):
        raise OrbitDataError("each OMM JSON record must be an object")
    return tuple(_record_from_omm(dict(row), ts) for row in rows)


def _load_omm_csv(path: Path, ts) -> tuple[OrbitSatellite, ...]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise OrbitDataError("OMM CSV contains no satellite records")
    return tuple(_record_from_omm(dict(row), ts) for row in rows)


def _load_tle(path: Path, ts) -> tuple[OrbitSatellite, ...]:
    raw = path.read_bytes()
    try:
        satellites = list(parse_tle_file(io.BytesIO(raw), ts=ts, skip_names=False))
    except Exception as exc:
        raise OrbitDataError(f"failed to parse TLE file {path}: {exc}") from exc
    if not satellites:
        raise OrbitDataError("TLE file contains no satellite records")
    records = []
    for satellite in satellites:
        object_id = satellite.model.intldesg.strip() or None
        records.append(
            OrbitSatellite(
                satellite=satellite,
                name=satellite.name or f"NORAD-{satellite.model.satnum}",
                norad_cat_id=str(satellite.model.satnum),
                object_id=object_id,
                epoch_utc=iso_utc(satellite.epoch.utc_datetime()),
                source_fields={},
            )
        )
    return tuple(records)


def load_catalog(path: Path, source_format: str = "auto") -> OrbitCatalog:
    if not path.is_file():
        raise FileNotFoundError(path)
    actual_format = detect_orbit_format(path, source_format)
    ts = timescale()
    if actual_format == "omm-json":
        satellites = _load_omm_json(path, ts)
    elif actual_format == "omm-csv":
        satellites = _load_omm_csv(path, ts)
    elif actual_format == "tle":
        satellites = _load_tle(path, ts)
    else:
        raise OrbitDataError(f"unsupported orbit format: {actual_format}")
    return OrbitCatalog(path.resolve(), actual_format, satellites)

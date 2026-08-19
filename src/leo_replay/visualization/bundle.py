from __future__ import annotations

import csv
import html
import json
import math
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from importlib.resources import files
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from leo_replay import __version__
from leo_replay.event_profile import load_document
from leo_replay.orbit.models import iso_utc, parse_utc, sha256_file, utc_now_iso


class VisualizationError(ValueError):
    """Raised when synchronized visualization input cannot be normalized."""


@dataclass(frozen=True)
class CommunicationSample:
    timestamp: datetime
    elapsed_sec: float
    delay_ms: float | None
    rtt_ms: float | None
    jitter_ms: float | None
    loss_pct: float | None
    rate_mbit: float | None
    note: str


@dataclass(frozen=True)
class VisibilitySample:
    timestamp: datetime
    norad_cat_id: str
    satellite_name: str
    visible: bool
    elevation_deg: float | None
    azimuth_deg: float | None
    slant_range_km: float | None
    stale_element: bool
    propagation_error: str


def _finite_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise VisualizationError(f"invalid JSON: {path}: {exc}") from exc


def _load_selection(path: Path) -> dict[str, Any]:
    value = _read_json(path)
    if not isinstance(value, dict):
        raise VisualizationError("historical selection input must be a JSON object")
    if value.get("selection_type") != "historical_orbit_element_selection":
        raise VisualizationError("selection input is not a historical element selection document")
    observations = value.get("observations")
    if not isinstance(observations, list) or not observations:
        raise VisualizationError("selection document contains no observations")
    return value


def _load_site(path: Path) -> dict[str, Any]:
    value = _read_json(path)
    if not isinstance(value, dict):
        raise VisualizationError("observer site must be a JSON object")
    required = ("site_id", "latitude_deg", "longitude_deg")
    missing = [key for key in required if key not in value]
    if missing:
        raise VisualizationError("observer site is missing fields: " + ", ".join(missing))
    latitude = _finite_float(value.get("latitude_deg"))
    longitude = _finite_float(value.get("longitude_deg"))
    elevation = _finite_float(value.get("elevation_m")) or 0.0
    if latitude is None or not -90 <= latitude <= 90:
        raise VisualizationError("site latitude_deg must be between -90 and 90")
    if longitude is None or not -180 <= longitude <= 180:
        raise VisualizationError("site longitude_deg must be between -180 and 180")
    return {
        "site_id": str(value["site_id"]),
        "name": str(value.get("name") or value["site_id"]),
        "latitude_deg": latitude,
        "longitude_deg": longitude,
        "elevation_m": elevation,
        "metadata": value.get("metadata") if isinstance(value.get("metadata"), dict) else {},
    }


def _normalize_position(selection: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(selection, Mapping):
        return None
    position = selection.get("position_at_observation")
    if not isinstance(position, Mapping):
        return None
    latitude = _finite_float(position.get("subpoint_latitude_deg"))
    longitude = _finite_float(position.get("subpoint_longitude_deg"))
    height = _finite_float(position.get("height_km"))
    if latitude is None or longitude is None:
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return {
        "latitude_deg": latitude,
        "longitude_deg": longitude,
        "height_km": height,
        "epoch_utc": selection.get("epoch_utc"),
        "creation_date_utc": selection.get("creation_date_utc"),
        "absolute_epoch_distance_sec": _finite_float(
            selection.get("absolute_epoch_distance_sec")
        ),
        "stale_element": bool(selection.get("stale_element")),
        "record_fingerprint": selection.get("record_fingerprint"),
        "propagation_error": str(position.get("propagation_error") or ""),
    }


def _load_profile(path: Path | None, start: datetime) -> list[CommunicationSample]:
    if path is None:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise VisualizationError(f"communication profile contains no rows: {path}")

    samples: list[CommunicationSample] = []
    for index, row in enumerate(rows, start=2):
        timestamp_raw = row.get("timestamp_utc") or row.get("time_utc")
        if timestamp_raw:
            timestamp = parse_utc(str(timestamp_raw))
            elapsed = (timestamp - start).total_seconds()
        else:
            elapsed_value = row.get("sec", row.get("elapsed_sec", row.get("time_sec")))
            elapsed = _finite_float(elapsed_value)
            if elapsed is None:
                raise VisualizationError(
                    f"profile row {index} needs timestamp_utc or sec/elapsed_sec/time_sec"
                )
            timestamp = start + timedelta(seconds=elapsed)

        samples.append(
            CommunicationSample(
                timestamp=timestamp,
                elapsed_sec=float(elapsed),
                delay_ms=_finite_float(row.get("delay_ms")),
                rtt_ms=_finite_float(row.get("rtt_ms", row.get("ping_rtt_ms"))),
                jitter_ms=_finite_float(row.get("jitter_ms")),
                loss_pct=_finite_float(row.get("loss_pct")),
                rate_mbit=_finite_float(
                    row.get("rate_mbit", row.get("throughput_mbps", row.get("rate_mbps")))
                ),
                note=str(row.get("note") or row.get("state") or ""),
            )
        )
    samples.sort(key=lambda sample: sample.timestamp)
    return samples


def _load_visibility(path: Path | None) -> list[VisibilitySample]:
    if path is None:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    samples: list[VisibilitySample] = []
    for index, row in enumerate(rows, start=2):
        timestamp_raw = row.get("timestamp_utc")
        cat_id = row.get("norad_cat_id")
        if not timestamp_raw or cat_id in (None, ""):
            raise VisualizationError(
                f"visibility row {index} needs timestamp_utc and norad_cat_id"
            )
        samples.append(
            VisibilitySample(
                timestamp=parse_utc(str(timestamp_raw)),
                norad_cat_id=str(cat_id),
                satellite_name=str(row.get("satellite_name") or f"NORAD-{cat_id}"),
                visible=_truthy(row.get("visible")),
                elevation_deg=_finite_float(row.get("elevation_deg")),
                azimuth_deg=_finite_float(row.get("azimuth_deg")),
                slant_range_km=_finite_float(row.get("slant_range_km")),
                stale_element=_truthy(row.get("stale_element")),
                propagation_error=str(row.get("propagation_error") or ""),
            )
        )
    return samples


def _load_events(path: Path | None, start: datetime) -> list[dict[str, Any]]:
    if path is None:
        return []
    document = load_document(path)
    events: list[dict[str, Any]] = []
    for event in document.get("events", []):
        start_sec = _finite_float(event.get("start_sec")) or 0.0
        end_sec = _finite_float(event.get("end_sec"))
        if end_sec is None:
            end_sec = start_sec + (_finite_float(event.get("duration_sec")) or 0.0)
        events.append(
            {
                "event_id": str(event.get("event_id") or ""),
                "event_type": str(event.get("event_type") or "custom"),
                "start_sec": start_sec,
                "end_sec": end_sec,
                "start_utc": iso_utc(start + timedelta(seconds=start_sec)),
                "end_utc": iso_utc(start + timedelta(seconds=end_sec)),
                "severity": int(_finite_float(event.get("severity")) or 0),
                "confidence": _finite_float(event.get("confidence")),
                "source_type": str(event.get("source_type") or ""),
            }
        )
    return events


def _latest_profile_sample(
    samples: Sequence[CommunicationSample], timestamp: datetime
) -> CommunicationSample | None:
    selected: CommunicationSample | None = None
    for sample in samples:
        if sample.timestamp <= timestamp:
            selected = sample
        else:
            break
    return selected or (samples[0] if samples else None)


def _nearest_visibility(
    samples: Sequence[VisibilitySample],
    timestamp: datetime,
    tolerance_sec: float,
) -> dict[str, VisibilitySample]:
    nearest: dict[str, tuple[float, VisibilitySample]] = {}
    for sample in samples:
        distance = abs((sample.timestamp - timestamp).total_seconds())
        if distance > tolerance_sec:
            continue
        previous = nearest.get(sample.norad_cat_id)
        if previous is None or distance < previous[0]:
            nearest[sample.norad_cat_id] = (distance, sample)
    return {cat_id: value[1] for cat_id, value in nearest.items()}


def _active_events(events: Sequence[dict[str, Any]], elapsed_sec: float) -> list[dict[str, Any]]:
    return [
        event
        for event in events
        if float(event["start_sec"]) <= elapsed_sec <= float(event["end_sec"])
    ]


def _source_entry(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return {
        "path": path.name,
        "name": path.name,
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def _json_script(value: Any) -> str:
    # Prevent a JSON string from terminating the surrounding script element.
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def _asset_text(name: str) -> str:
    return files("leo_replay.visualization.assets").joinpath(name).read_text(encoding="utf-8")


def _prepare_output_dir(path: Path, force: bool) -> None:
    if path.exists():
        if not path.is_dir():
            raise VisualizationError(f"output path exists and is not a directory: {path}")
        existing = [item for item in path.iterdir() if item.name != ".gitkeep"]
        if existing and not force:
            raise VisualizationError(
                f"output directory is not empty: {path}; use --force to replace it"
            )
        if force:
            for item in existing:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
    path.mkdir(parents=True, exist_ok=True)


def _timeline_bounds(frames: Sequence[dict[str, Any]]) -> dict[str, Any]:
    latitudes: list[float] = []
    longitudes: list[float] = []
    for frame in frames:
        for satellite in frame["satellites"]:
            for key in ("causal", "retrospective"):
                position = satellite.get(key)
                if position:
                    latitudes.append(float(position["latitude_deg"]))
                    longitudes.append(float(position["longitude_deg"]))
    return {
        "latitude_min": min(latitudes) if latitudes else -90.0,
        "latitude_max": max(latitudes) if latitudes else 90.0,
        "longitude_min": min(longitudes) if longitudes else -180.0,
        "longitude_max": max(longitudes) if longitudes else 180.0,
    }


def build_visualization_bundle(
    *,
    selection_path: Path,
    site_path: Path,
    output_dir: Path,
    profile_path: Path | None = None,
    visibility_path: Path | None = None,
    events_path: Path | None = None,
    profile_start_utc: str | None = None,
    title: str | None = None,
    visibility_tolerance_sec: float = 0.75,
    maximum_satellites: int = 20000,
    force: bool = False,
) -> dict[str, Any]:
    if visibility_tolerance_sec < 0:
        raise VisualizationError("visibility_tolerance_sec must be >= 0")
    if maximum_satellites <= 0:
        raise VisualizationError("maximum_satellites must be > 0")

    selection = _load_selection(selection_path)
    site = _load_site(site_path)
    observations = sorted(
        selection["observations"], key=lambda row: parse_utc(str(row["observation_time_utc"]))
    )
    first_time = parse_utc(str(observations[0]["observation_time_utc"]))
    profile_start = parse_utc(profile_start_utc) if profile_start_utc else first_time
    profile = _load_profile(profile_path, profile_start)
    visibility = _load_visibility(visibility_path)
    events = _load_events(events_path, profile_start)

    unique_satellites = {
        str(satellite.get("norad_cat_id"))
        for observation in observations
        for satellite in observation.get("satellites", [])
    }
    if len(unique_satellites) > maximum_satellites:
        raise VisualizationError(
            f"selection has {len(unique_satellites)} satellites, above --maximum-satellites={maximum_satellites}"
        )

    frames: list[dict[str, Any]] = []
    causal_count = 0
    retrospective_count = 0
    visible_count = 0
    maximum_delta: float | None = None
    for observation in observations:
        timestamp = parse_utc(str(observation["observation_time_utc"]))
        elapsed = (timestamp - profile_start).total_seconds()
        visibility_by_satellite = _nearest_visibility(
            visibility, timestamp, visibility_tolerance_sec
        )
        satellites: list[dict[str, Any]] = []
        for raw in observation.get("satellites", []):
            if not isinstance(raw, Mapping):
                continue
            cat_id = str(raw.get("norad_cat_id") or "")
            causal = _normalize_position(raw.get("causal"))
            retrospective = _normalize_position(raw.get("retrospective"))
            if causal:
                causal_count += 1
            if retrospective:
                retrospective_count += 1
            visibility_sample = visibility_by_satellite.get(cat_id)
            visible = bool(visibility_sample and visibility_sample.visible)
            if visible:
                visible_count += 1
            comparison = raw.get("comparison") if isinstance(raw.get("comparison"), Mapping) else {}
            delta = _finite_float(comparison.get("causal_retrospective_position_delta_km"))
            if delta is not None:
                maximum_delta = delta if maximum_delta is None else max(maximum_delta, delta)
            satellites.append(
                {
                    "norad_cat_id": cat_id,
                    "object_name": str(raw.get("object_name") or f"NORAD-{cat_id}"),
                    "causal": causal,
                    "retrospective": retrospective,
                    "position_delta_km": delta,
                    "flags": list(raw.get("flags") or []),
                    "visibility": (
                        {
                            "visible": visibility_sample.visible,
                            "elevation_deg": visibility_sample.elevation_deg,
                            "azimuth_deg": visibility_sample.azimuth_deg,
                            "slant_range_km": visibility_sample.slant_range_km,
                            "stale_element": visibility_sample.stale_element,
                            "propagation_error": visibility_sample.propagation_error,
                        }
                        if visibility_sample
                        else None
                    ),
                }
            )
        satellites.sort(key=lambda item: (item["object_name"], item["norad_cat_id"]))
        communication = _latest_profile_sample(profile, timestamp)
        frames.append(
            {
                "timestamp_utc": iso_utc(timestamp),
                "elapsed_sec": elapsed,
                "communication": (
                    {
                        "delay_ms": communication.delay_ms,
                        "rtt_ms": communication.rtt_ms,
                        "jitter_ms": communication.jitter_ms,
                        "loss_pct": communication.loss_pct,
                        "rate_mbit": communication.rate_mbit,
                        "note": communication.note,
                    }
                    if communication
                    else None
                ),
                "events": _active_events(events, elapsed),
                "satellites": satellites,
                "summary": {
                    "satellite_count": len(satellites),
                    "visible_count": sum(
                        1 for satellite in satellites if satellite["visibility"] and satellite["visibility"]["visible"]
                    ),
                    "causal_position_count": sum(1 for satellite in satellites if satellite["causal"]),
                    "retrospective_position_count": sum(
                        1 for satellite in satellites if satellite["retrospective"]
                    ),
                },
            }
        )

    document = {
        "schema_version": "1.0",
        "visualization_type": "orbit_communication_timeline",
        "generated_at_utc": utc_now_iso(),
        "generator": f"leo-replay {__version__}",
        "title": title or "LEO Orbit Context and Communication Timeline",
        "semantics": {
            "causal": "Orbital element available by the observation-time knowledge cutoff.",
            "retrospective": "Orbital element with epoch nearest to the observation time.",
            "satellite_identity": "Map points are geometric orbit reconstructions, not proof of the serving satellite.",
            "uncertainty": "Position deltas are sensitivity indicators, not statistical confidence bounds.",
        },
        "site": site,
        "source": {
            "selection": _source_entry(selection_path),
            "profile": _source_entry(profile_path),
            "visibility": _source_entry(visibility_path),
            "events": _source_entry(events_path),
            "selection_policy": selection.get("policy"),
        },
        "timeline": {
            "start_utc": frames[0]["timestamp_utc"],
            "end_utc": frames[-1]["timestamp_utc"],
            "frame_count": len(frames),
            "profile_start_utc": iso_utc(profile_start),
        },
        "events": events,
        "frames": frames,
        "summary": {
            "frame_count": len(frames),
            "satellite_count": len(unique_satellites),
            "causal_position_count": causal_count,
            "retrospective_position_count": retrospective_count,
            "visible_observation_count": visible_count,
            "maximum_causal_retrospective_position_delta_km": maximum_delta,
        },
        "map_bounds": _timeline_bounds(frames),
    }

    _prepare_output_dir(output_dir, force)
    data_path = output_dir / "data.json"
    data_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    template = _asset_text("index.template.html")
    rendered = (
        template.replace("{{TITLE}}", html.escape(str(document["title"])))
        .replace("{{STYLE}}", _asset_text("style.css"))
        .replace("{{WORLD_DATA}}", _json_script(_read_json(files("leo_replay.visualization.assets").joinpath("world-land.geojson"))))
        .replace("{{BUNDLE_DATA}}", _json_script(document))
        .replace("{{SCRIPT}}", _asset_text("app.js"))
    )
    index_path = output_dir / "index.html"
    index_path.write_text(rendered, encoding="utf-8")

    readme_path = output_dir / "README.txt"
    readme_path.write_text(
        "LEO Replay synchronized visualization bundle\n\n"
        "Open index.html directly in a modern browser, or run:\n"
        "  leo-replay viz serve --input-dir .\n\n"
        "The bundle is self-contained and makes no external network requests.\n",
        encoding="utf-8",
    )

    manifest = {
        "schema_version": "1.0",
        "manifest_type": "visualization_bundle",
        "generated_at_utc": utc_now_iso(),
        "generator": f"leo-replay {__version__}",
        "files": [
            {
                "path": path.name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in (index_path, data_path, readme_path)
        ],
        "summary": document["summary"],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "status": "built",
        "output_dir": str(output_dir),
        "index": str(index_path),
        "data": str(data_path),
        "manifest": str(manifest_path),
        "frames": len(frames),
        "satellites": len(unique_satellites),
    }

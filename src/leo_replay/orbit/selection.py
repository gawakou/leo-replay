from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from skyfield.api import EarthSatellite, wgs84

from leo_replay import __version__

from .catalog import timescale
from .models import OrbitDataError, iso_utc, parse_utc, sha256_file, utc_now_iso
from .snapshot import load_manifest, verify_snapshot


class HistoricalSelectionError(OrbitDataError):
    """Raised when historical orbital elements cannot be selected safely."""


@dataclass(frozen=True)
class HistoricalElement:
    source_index: int
    fields: dict[str, Any]
    norad_cat_id: str
    object_name: str
    object_id: str | None
    epoch: datetime
    creation_date: datetime | None
    gp_id: int | None
    element_set_no: int | None
    fingerprint: str


@dataclass(frozen=True)
class HistoricalElementCollection:
    source_path: Path
    source_format: str
    source_sha256: str
    records: tuple[HistoricalElement, ...]
    provider: str | None = None
    request_fingerprint: str | None = None
    snapshot_manifest_sha256: str | None = None

    def select(self, selectors: Iterable[str] | None) -> "HistoricalElementCollection":
        requested = [value.strip().lower() for value in (selectors or []) if value.strip()]
        if not requested:
            return self
        selected: list[HistoricalElement] = []
        for record in self.records:
            values = {
                record.norad_cat_id.lower(),
                record.object_name.lower(),
                (record.object_id or "").lower(),
            }
            if any(item in values or item in record.object_name.lower() for item in requested):
                selected.append(record)
        if not selected:
            raise HistoricalSelectionError(
                "no historical orbit records matched selectors: " + ", ".join(requested)
            )
        return HistoricalElementCollection(
            source_path=self.source_path,
            source_format=self.source_format,
            source_sha256=self.source_sha256,
            records=tuple(selected),
            provider=self.provider,
            request_fingerprint=self.request_fingerprint,
            snapshot_manifest_sha256=self.snapshot_manifest_sha256,
        )


@dataclass(frozen=True)
class SelectionPolicy:
    mode: str = "compare"
    availability_lag_sec: float = 0.0
    stale_after_days: float = 14.0
    position_warning_km: float = 10.0
    missing_creation_date_policy: str = "exclude"
    include_element_fields: bool = False

    def validate(self) -> None:
        if self.mode not in {"causal", "retrospective", "compare"}:
            raise HistoricalSelectionError("mode must be causal, retrospective, or compare")
        if self.availability_lag_sec < 0:
            raise HistoricalSelectionError("availability_lag_sec must be >= 0")
        if self.stale_after_days <= 0:
            raise HistoricalSelectionError("stale_after_days must be > 0")
        if self.position_warning_km <= 0:
            raise HistoricalSelectionError("position_warning_km must be > 0")
        if self.missing_creation_date_policy not in {"exclude", "error"}:
            raise HistoricalSelectionError(
                "missing_creation_date_policy must be exclude or error"
            )


def _canonical_record_fingerprint(fields: Mapping[str, Any]) -> str:
    body = json.dumps(
        dict(fields), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_record(fields: Mapping[str, Any], source_index: int) -> HistoricalElement:
    cat_id = fields.get("NORAD_CAT_ID")
    epoch_value = fields.get("EPOCH")
    if cat_id in (None, "") or epoch_value in (None, ""):
        raise HistoricalSelectionError(
            f"historical OMM record {source_index} is missing NORAD_CAT_ID or EPOCH"
        )
    creation_raw = fields.get("CREATION_DATE")
    creation_date = None
    if creation_raw not in (None, ""):
        creation_date = parse_utc(str(creation_raw))
    object_id = fields.get("OBJECT_ID")
    normalized = dict(fields)
    return HistoricalElement(
        source_index=source_index,
        fields=normalized,
        norad_cat_id=str(cat_id),
        object_name=str(fields.get("OBJECT_NAME") or f"NORAD-{cat_id}"),
        object_id=str(object_id) if object_id not in (None, "") else None,
        epoch=parse_utc(str(epoch_value)),
        creation_date=creation_date,
        gp_id=_optional_int(fields.get("GP_ID")),
        element_set_no=_optional_int(fields.get("ELEMENT_SET_NO")),
        fingerprint=_canonical_record_fingerprint(normalized),
    )


def _load_json_records(path: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise HistoricalSelectionError(f"invalid historical OMM JSON: {path}: {exc}") from exc
    if isinstance(value, dict) and isinstance(value.get("data"), list):
        value = value["data"]
    elif isinstance(value, dict):
        value = [value]
    if not isinstance(value, list) or not value:
        raise HistoricalSelectionError("historical OMM JSON contains no records")
    if not all(isinstance(row, dict) for row in value):
        raise HistoricalSelectionError("historical OMM JSON records must be objects")
    return [dict(row) for row in value]


def _load_csv_records(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise HistoricalSelectionError("historical OMM CSV contains no records")
    return [dict(row) for row in rows]


def _resolve_source(path: Path) -> tuple[Path, str, dict[str, Any] | None, str | None]:
    path = path.resolve()
    manifest: dict[str, Any] | None = None
    manifest_sha256: str | None = None
    if path.is_dir():
        verify_snapshot(path)
        manifest = load_manifest(path)
        relative = manifest.get("combined_body_file")
        if not isinstance(relative, str) or not relative:
            raise HistoricalSelectionError("snapshot manifest has no combined_body_file")
        source = (path / relative).resolve()
        try:
            source.relative_to(path)
        except ValueError as exc:
            raise HistoricalSelectionError(
                "snapshot combined_body_file escapes its directory"
            ) from exc
        manifest_sha256 = sha256_file(path / "manifest.json")
        source_format = str(manifest.get("format") or "").lower()
    else:
        source = path
        suffix = source.suffix.lower()
        source_format = "json" if suffix == ".json" else "csv" if suffix == ".csv" else ""
    if not source.is_file():
        raise FileNotFoundError(source)
    if source_format not in {"json", "csv"}:
        raise HistoricalSelectionError(
            "historical element selection requires OMM JSON or CSV; TLE lacks CREATION_DATE"
        )
    return source, source_format, manifest, manifest_sha256


def load_historical_elements(path: Path) -> HistoricalElementCollection:
    source, source_format, manifest, manifest_sha256 = _resolve_source(path)
    raw_records = (
        _load_json_records(source)
        if source_format == "json"
        else _load_csv_records(source)
    )
    records = tuple(_parse_record(row, index) for index, row in enumerate(raw_records))
    return HistoricalElementCollection(
        source_path=source,
        source_format=f"omm-{source_format}",
        source_sha256=sha256_file(source),
        records=records,
        provider=str(manifest.get("provider")) if manifest and manifest.get("provider") else None,
        request_fingerprint=(
            str(manifest.get("request_fingerprint"))
            if manifest and manifest.get("request_fingerprint")
            else None
        ),
        snapshot_manifest_sha256=manifest_sha256,
    )


def build_observation_times(
    *,
    times: Sequence[str] | None = None,
    start: str | None = None,
    duration_sec: float | None = None,
    step_sec: float | None = None,
) -> tuple[datetime, ...]:
    direct = [parse_utc(value) for value in (times or [])]
    range_requested = start is not None or duration_sec is not None
    if direct and range_requested:
        raise HistoricalSelectionError(
            "use either --time values or --start/--duration-sec/--step-sec"
        )
    if direct:
        return tuple(sorted(set(direct)))
    if not range_requested:
        raise HistoricalSelectionError("at least one observation time is required")
    if start is None or duration_sec is None:
        raise HistoricalSelectionError("time ranges require --start and --duration-sec")
    step = 1.0 if step_sec is None else step_sec
    if duration_sec < 0:
        raise HistoricalSelectionError("duration_sec must be >= 0")
    if step <= 0:
        raise HistoricalSelectionError("step_sec must be > 0")
    beginning = parse_utc(start)
    result: list[datetime] = []
    offset = 0.0
    epsilon = 1e-9
    while offset <= duration_sec + epsilon:
        result.append(beginning + timedelta(seconds=offset))
        offset += step
    if not result:
        result.append(beginning)
    return tuple(result)


def _numeric_tiebreak(record: HistoricalElement) -> tuple[int, int, int]:
    return (
        record.gp_id if record.gp_id is not None else -1,
        record.element_set_no if record.element_set_no is not None else -1,
        record.source_index,
    )


def _select_retrospective(
    records: Sequence[HistoricalElement], observation: datetime
) -> HistoricalElement | None:
    if not records:
        return None
    return min(
        records,
        key=lambda record: (
            abs((record.epoch - observation).total_seconds()),
            -record.creation_date.timestamp() if record.creation_date else float("inf"),
            tuple(-value for value in _numeric_tiebreak(record)),
        ),
    )


def _select_causal(
    records: Sequence[HistoricalElement],
    observation: datetime,
    policy: SelectionPolicy,
) -> tuple[HistoricalElement | None, int, int]:
    cutoff = observation - timedelta(seconds=policy.availability_lag_sec)
    missing = sum(record.creation_date is None for record in records)
    if missing and policy.missing_creation_date_policy == "error":
        raise HistoricalSelectionError(
            f"{missing} historical records have no CREATION_DATE; causal selection cannot continue"
        )
    eligible = [
        record
        for record in records
        if record.creation_date is not None and record.creation_date <= cutoff
    ]
    if not eligible:
        return None, 0, missing
    selected = max(
        eligible,
        key=lambda record: (
            record.creation_date,
            -abs((record.epoch - observation).total_seconds()),
            _numeric_tiebreak(record),
        ),
    )
    return selected, len(eligible), missing


def _skyfield_time(ts, value: datetime):
    return ts.from_datetime(value)


def _position(record: HistoricalElement, observation: datetime, ts) -> dict[str, Any]:
    try:
        satellite = EarthSatellite.from_omm(ts, record.fields)
        geocentric = satellite.at(_skyfield_time(ts, observation))
        xyz = [float(value) for value in geocentric.position.km]
        message = geocentric.message
        if isinstance(message, (list, tuple)):
            message = "; ".join(str(item) for item in message if item)
        if any(not math.isfinite(value) for value in xyz):
            raise HistoricalSelectionError("SGP4 returned a non-finite satellite position")
        subpoint = wgs84.subpoint_of(geocentric)
        return {
            "gcrs_km": xyz,
            "subpoint_latitude_deg": float(subpoint.latitude.degrees),
            "subpoint_longitude_deg": float(subpoint.longitude.degrees),
            "height_km": float(subpoint.elevation.km),
            "propagation_error": str(message or ""),
        }
    except Exception as exc:
        return {
            "gcrs_km": None,
            "subpoint_latitude_deg": None,
            "subpoint_longitude_deg": None,
            "height_km": None,
            "propagation_error": str(exc),
        }


def _distance_between(
    position_a: Mapping[str, Any] | None,
    position_b: Mapping[str, Any] | None,
) -> float | None:
    if not position_a or not position_b:
        return None
    a = position_a.get("gcrs_km")
    b = position_b.get("gcrs_km")
    if not isinstance(a, list) or not isinstance(b, list) or len(a) != 3 or len(b) != 3:
        return None
    return math.sqrt(sum((float(left) - float(right)) ** 2 for left, right in zip(a, b)))


def _selection_document(
    record: HistoricalElement | None,
    observation: datetime,
    ts,
    stale_after_days: float,
    include_element_fields: bool,
) -> dict[str, Any] | None:
    if record is None:
        return None
    epoch_distance = (record.epoch - observation).total_seconds()
    creation_age = (
        (observation - record.creation_date).total_seconds()
        if record.creation_date is not None
        else None
    )
    document = {
        "source_index": record.source_index,
        "record_fingerprint": record.fingerprint,
        "norad_cat_id": record.norad_cat_id,
        "object_name": record.object_name,
        "object_id": record.object_id,
        "epoch_utc": iso_utc(record.epoch),
        "creation_date_utc": iso_utc(record.creation_date) if record.creation_date else None,
        "gp_id": record.gp_id,
        "element_set_no": record.element_set_no,
        "signed_epoch_offset_sec": epoch_distance,
        "absolute_epoch_distance_sec": abs(epoch_distance),
        "creation_age_at_observation_sec": creation_age,
        "stale_element": abs(epoch_distance) > stale_after_days * 86400.0,
        "position_at_observation": _position(record, observation, ts),
    }
    if include_element_fields:
        document["element_fields"] = dict(record.fields)
    return document


def _bracketing_sensitivity(
    records: Sequence[HistoricalElement], observation: datetime, ts
) -> dict[str, Any]:
    before = [record for record in records if record.epoch <= observation]
    after = [record for record in records if record.epoch >= observation]
    before_record = (
        max(before, key=lambda record: (record.epoch, _numeric_tiebreak(record)))
        if before
        else None
    )
    after_record = (
        min(
            after,
            key=lambda record: (
                record.epoch, tuple(-value for value in _numeric_tiebreak(record))
            ),
        )
        if after
        else None
    )
    before_position = _position(before_record, observation, ts) if before_record else None
    after_position = _position(after_record, observation, ts) if after_record else None
    spread = None
    if before_record and after_record and before_record.fingerprint != after_record.fingerprint:
        spread = _distance_between(before_position, after_position)
    return {
        "interpretation": "sensitivity indicator, not a statistical error bound",
        "before_epoch_utc": iso_utc(before_record.epoch) if before_record else None,
        "before_record_fingerprint": before_record.fingerprint if before_record else None,
        "after_epoch_utc": iso_utc(after_record.epoch) if after_record else None,
        "after_record_fingerprint": after_record.fingerprint if after_record else None,
        "position_spread_km": spread,
    }


def select_historical_elements(
    collection: HistoricalElementCollection,
    observation_times: Sequence[datetime],
    policy: SelectionPolicy,
) -> dict[str, Any]:
    policy.validate()
    if not observation_times:
        raise HistoricalSelectionError("at least one observation time is required")
    grouped: dict[str, list[HistoricalElement]] = {}
    for record in collection.records:
        grouped.setdefault(record.norad_cat_id, []).append(record)
    for records in grouped.values():
        records.sort(
            key=lambda item: (
                item.epoch,
                item.creation_date or datetime.min.replace(tzinfo=item.epoch.tzinfo),
                item.source_index,
            )
        )

    ts = timescale()
    observations: list[dict[str, Any]] = []
    summary = {
        "observation_count": len(observation_times),
        "satellite_count": len(grouped),
        "causal_selected": 0,
        "retrospective_selected": 0,
        "causal_unavailable": 0,
        "stale_selections": 0,
        "position_comparisons": 0,
        "position_warning_count": 0,
        "maximum_causal_retrospective_position_delta_km": None,
        "maximum_bracketing_position_spread_km": None,
    }

    max_delta: float | None = None
    max_spread: float | None = None
    for observation in observation_times:
        satellite_documents: list[dict[str, Any]] = []
        cutoff = observation - timedelta(seconds=policy.availability_lag_sec)
        for cat_id in sorted(
            grouped, key=lambda value: (0, int(value)) if value.isdigit() else (1, value)
        ):
            records = grouped[cat_id]
            causal_record = None
            causal_eligible_count = 0
            missing_creation_count = sum(record.creation_date is None for record in records)
            retrospective_record = None
            if policy.mode in {"causal", "compare"}:
                causal_record, causal_eligible_count, missing_creation_count = _select_causal(
                    records, observation, policy
                )
            if policy.mode in {"retrospective", "compare"}:
                retrospective_record = _select_retrospective(records, observation)

            causal_document = _selection_document(
                causal_record,
                observation,
                ts,
                policy.stale_after_days,
                policy.include_element_fields,
            )
            retrospective_document = _selection_document(
                retrospective_record,
                observation,
                ts,
                policy.stale_after_days,
                policy.include_element_fields,
            )
            comparison_delta = _distance_between(
                causal_document.get("position_at_observation") if causal_document else None,
                retrospective_document.get("position_at_observation")
                if retrospective_document
                else None,
            )
            sensitivity = _bracketing_sensitivity(records, observation, ts)
            spread = sensitivity["position_spread_km"]
            flags: list[str] = []
            if policy.mode in {"causal", "compare"} and causal_document is None:
                flags.append("causal_element_unavailable")
                summary["causal_unavailable"] += 1
            if missing_creation_count:
                flags.append("records_missing_creation_date")
            for selection in (causal_document, retrospective_document):
                if selection and selection["stale_element"]:
                    flags.append("stale_selected_element")
                    summary["stale_selections"] += 1
                    break
                if selection and selection["position_at_observation"]["propagation_error"]:
                    flags.append("propagation_error")
            if comparison_delta is not None:
                summary["position_comparisons"] += 1
                max_delta = (
                    comparison_delta
                    if max_delta is None
                    else max(max_delta, comparison_delta)
                )
                if comparison_delta > policy.position_warning_km:
                    flags.append("causal_retrospective_position_delta_warning")
                    summary["position_warning_count"] += 1
            if spread is not None:
                max_spread = spread if max_spread is None else max(max_spread, spread)
                if spread > policy.position_warning_km:
                    flags.append("bracketing_position_spread_warning")
            if causal_document:
                summary["causal_selected"] += 1
            if retrospective_document:
                summary["retrospective_selected"] += 1

            satellite_documents.append(
                {
                    "norad_cat_id": cat_id,
                    "object_name": records[-1].object_name,
                    "object_id": next((r.object_id for r in records if r.object_id), None),
                    "available_record_count": len(records),
                    "records_with_creation_date": len(records) - missing_creation_count,
                    "causal_eligible_count": causal_eligible_count,
                    "causal": causal_document,
                    "retrospective": retrospective_document,
                    "comparison": {
                        "causal_retrospective_position_delta_km": comparison_delta,
                        "same_element": (
                            causal_record is not None
                            and retrospective_record is not None
                            and causal_record.fingerprint == retrospective_record.fingerprint
                        ),
                    },
                    "bracketing_element_sensitivity": sensitivity,
                    "flags": sorted(set(flags)),
                }
            )
        observations.append(
            {
                "observation_time_utc": iso_utc(observation),
                "causal_knowledge_cutoff_utc": iso_utc(cutoff),
                "satellites": satellite_documents,
            }
        )

    summary["maximum_causal_retrospective_position_delta_km"] = max_delta
    summary["maximum_bracketing_position_spread_km"] = max_spread
    return {
        "schema_version": "1.0",
        "selection_type": "historical_orbit_element_selection",
        "generated_at_utc": utc_now_iso(),
        "generator": f"leo-replay {__version__}",
        "source": {
            "path": str(collection.source_path),
            "format": collection.source_format,
            "sha256": collection.source_sha256,
            "record_count": len(collection.records),
            "provider": collection.provider,
            "request_fingerprint": collection.request_fingerprint,
            "snapshot_manifest_sha256": collection.snapshot_manifest_sha256,
        },
        "policy": {
            "mode": policy.mode,
            "causal_rule": "latest CREATION_DATE at or before the knowledge cutoff",
            "retrospective_rule": "minimum absolute EPOCH distance from observation time",
            "availability_lag_sec": policy.availability_lag_sec,
            "missing_creation_date_policy": policy.missing_creation_date_policy,
            "stale_after_days": policy.stale_after_days,
            "position_warning_km": policy.position_warning_km,
            "include_element_fields": policy.include_element_fields,
            "position_delta_interpretation": (
                "difference between two SGP4 propagations, not a statistical accuracy bound"
            ),
        },
        "summary": summary,
        "observations": observations,
    }


def save_selection_document(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

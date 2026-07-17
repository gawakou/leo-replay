from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "1.0"
PROFILE_TYPE = "event"
SOURCE_TYPES = {"MEASURED", "DERIVED", "INFERRED", "SYNTHETIC"}
EVENT_TYPES = {
    "degradation_suspected",
    "backhaul_degradation_suspected",
    "handover_suspected",
    "outage_suspected",
    "obstruction_suspected",
    "collapse_suspected",
    "custom",
}


class EventProfileError(ValueError):
    """Raised when an event profile is structurally invalid."""


def _float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _event_id(index: int) -> str:
    return f"EV-{index:04d}"


def is_v1_document(data: Any) -> bool:
    return isinstance(data, dict) and data.get("profile_type") == PROFILE_TYPE and isinstance(
        data.get("events"), list
    )


def legacy_event_to_v1(row: dict[str, Any], index: int) -> dict[str, Any]:
    start_sec = _float(row.get("start_sec"))
    end_sec = _float(row.get("end_sec"), start_sec + _float(row.get("duration_sec")))
    duration_sec = _float(row.get("duration_sec"), max(0.0, end_sec - start_sec))
    if end_sec <= start_sec and duration_sec > 0:
        end_sec = start_sec + duration_sec
    duration_sec = max(0.0, end_sec - start_sec)

    event_type = str(row.get("event", row.get("event_type", "custom"))) or "custom"
    severity = max(0, min(4, _int(row.get("severity"))))

    observed_rate = _float(row.get("avg_rate_mbps", row.get("rate_mbit")))
    observed_delay = _float(row.get("avg_delay_ms", row.get("delay_ms")))
    observed_jitter = _float(row.get("jitter_ms"))
    observed_loss = _float(row.get("max_loss_pct", row.get("loss_pct")))

    calibrated_delay = _float(row.get("calibrated_delay_ms"))
    calibrated_jitter = _float(row.get("calibrated_jitter_ms"))
    calibrated_spike = _float(row.get("calibrated_spike_ms"))

    parameters = {
        "rate_mbit": observed_rate,
        "delay_ms": calibrated_delay if calibrated_delay > 0 else observed_delay,
        "jitter_ms": calibrated_jitter if calibrated_jitter > 0 else observed_jitter,
        "loss_pct": observed_loss,
        "spike_ms": calibrated_spike,
    }

    observations = {
        "bins": _int(row.get("bins")),
        "avg_rate_mbps": observed_rate,
        "max_loss_pct": observed_loss,
        "avg_delay_ms": observed_delay,
        "avg_ping_rtt_ms": _float(row.get("avg_ping_rtt_ms")),
        "max_ping_timeout_ratio": _float(row.get("max_ping_timeout_ratio")),
        "dominant_grpc_state": str(row.get("dominant_grpc_state", "")),
        "avg_pop_ping_latency_ms": _float(row.get("avg_pop_ping_latency_ms")),
        "max_fraction_obstructed": _float(row.get("max_fraction_obstructed")),
    }

    calibration_keys = {
        "calibrated_delay_ms",
        "delay_extra_ms",
        "calibrated_jitter_ms",
        "jitter_correction_ms",
        "calibrated_spike_ms",
        "spike_correction_ms",
        "calibration_method",
        "reference_avg_delay_ms",
        "measured_window_avg_rtt_ms",
        "replay_window_avg_rtt_ms",
        "measured_window_std_rtt_ms",
        "replay_window_std_rtt_ms",
        "measured_window_spike_rtt_ms",
        "replay_window_spike_rtt_ms",
        "rtt_error_ms",
        "jitter_error_ms",
        "spike_error_ms",
        "delay_correction_ms",
    }
    calibration = {key: row[key] for key in calibration_keys if key in row}

    return {
        "event_id": str(row.get("event_id", _event_id(index))),
        "event_type": event_type,
        "start_sec": round(start_sec, 6),
        "end_sec": round(end_sec, 6),
        "duration_sec": round(duration_sec, 6),
        "severity": severity,
        "confidence": max(0.0, min(1.0, _float(row.get("confidence"), 0.5))),
        "source_type": str(row.get("source_type", "DERIVED")).upper(),
        "parameters": parameters,
        "observations": observations,
        "calibration": calibration,
    }


def v1_event_to_legacy(event: dict[str, Any]) -> dict[str, Any]:
    parameters = event.get("parameters") or {}
    observations = event.get("observations") or {}
    calibration = event.get("calibration") or {}

    row: dict[str, Any] = {
        "event_id": event.get("event_id", ""),
        "start_sec": _float(event.get("start_sec")),
        "end_sec": _float(event.get("end_sec")),
        "duration_sec": _float(event.get("duration_sec")),
        "event": str(event.get("event_type", "custom")),
        "severity": _int(event.get("severity")),
        "confidence": _float(event.get("confidence"), 0.5),
        "source_type": str(event.get("source_type", "DERIVED")),
        "bins": _int(observations.get("bins")),
        "avg_rate_mbps": _float(
            observations.get("avg_rate_mbps", parameters.get("rate_mbit"))
        ),
        "max_loss_pct": _float(
            observations.get("max_loss_pct", parameters.get("loss_pct"))
        ),
        "avg_delay_ms": _float(
            observations.get("avg_delay_ms", parameters.get("delay_ms"))
        ),
        "avg_ping_rtt_ms": _float(observations.get("avg_ping_rtt_ms")),
        "max_ping_timeout_ratio": _float(observations.get("max_ping_timeout_ratio")),
        "dominant_grpc_state": str(observations.get("dominant_grpc_state", "")),
        "avg_pop_ping_latency_ms": _float(observations.get("avg_pop_ping_latency_ms")),
        "max_fraction_obstructed": _float(observations.get("max_fraction_obstructed")),
        "replay_rate_mbps": _float(parameters.get("rate_mbit")),
        "replay_delay_ms": _float(parameters.get("delay_ms")),
        "replay_jitter_ms": _float(parameters.get("jitter_ms")),
        "replay_loss_pct": _float(parameters.get("loss_pct")),
        "replay_spike_ms": _float(parameters.get("spike_ms")),
    }
    row.update(calibration)
    return row


def create_document(
    legacy_events: Iterable[dict[str, Any]],
    *,
    baseline: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    document = {
        "schema_version": SCHEMA_VERSION,
        "profile_type": PROFILE_TYPE,
        "metadata": {
            "created_at": _now_iso(),
            "generator": "leo-replay",
            "time_reference": "relative",
        },
        "baseline": {
            "rate_mbit": 0.0,
            "delay_ms": 0.0,
            "jitter_ms": 0.0,
            "loss_pct": 0.0,
        },
        "events": [legacy_event_to_v1(row, i) for i, row in enumerate(legacy_events, start=1)],
    }
    if metadata:
        document["metadata"].update(metadata)
    if baseline:
        document["baseline"].update(baseline)
    return document


def normalize_document(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        return create_document(data)
    if not isinstance(data, dict):
        raise EventProfileError("Event profile must be a JSON object or a legacy JSON array")
    if not is_v1_document(data):
        raise EventProfileError("Unsupported event profile object")
    document = copy.deepcopy(data)
    document.setdefault("schema_version", SCHEMA_VERSION)
    document.setdefault("metadata", {})
    document.setdefault("baseline", {})
    return document


def _validate_direction_mapping(mapping: Any, path: str, errors: list[str]) -> None:
    if not isinstance(mapping, dict):
        errors.append(f"{path} must be an object")
        return
    for direction in ("forward", "reverse"):
        condition = mapping.get(direction)
        if not isinstance(condition, dict):
            errors.append(f"{path}.{direction} must be an object")
            continue
        for key in ("rate_mbit", "delay_ms", "jitter_ms", "loss_pct"):
            value = _float(condition.get(key), math.nan)
            if not math.isfinite(value) or value < 0:
                errors.append(f"{path}.{direction}.{key} must be >= 0")
        for key in ("reorder_pct", "correlation_pct"):
            if key in condition:
                value = _float(condition.get(key), math.nan)
                if not math.isfinite(value) or not 0 <= value <= 100:
                    errors.append(f"{path}.{direction}.{key} must be in [0, 100]")
        loss = _float(condition.get("loss_pct"), math.nan)
        if math.isfinite(loss) and loss > 100:
            errors.append(f"{path}.{direction}.loss_pct must be <= 100")


def validate_document(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if document.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if document.get("profile_type") != PROFILE_TYPE:
        errors.append(f"profile_type must be {PROFILE_TYPE}")
    baseline = document.get("baseline")
    if isinstance(baseline, dict) and "directions" in baseline:
        _validate_direction_mapping(baseline.get("directions"), "baseline.directions", errors)

    events = document.get("events")
    if not isinstance(events, list):
        return errors + ["events must be an array"]

    seen_ids: set[str] = set()
    previous_start = -math.inf
    for index, event in enumerate(events):
        path = f"events[{index}]"
        if not isinstance(event, dict):
            errors.append(f"{path} must be an object")
            continue
        event_id = str(event.get("event_id", ""))
        if not event_id:
            errors.append(f"{path}.event_id is required")
        elif event_id in seen_ids:
            errors.append(f"{path}.event_id is duplicated: {event_id}")
        seen_ids.add(event_id)

        event_type = str(event.get("event_type", ""))
        if not event_type:
            errors.append(f"{path}.event_type is required")

        start = _float(event.get("start_sec"), math.nan)
        end = _float(event.get("end_sec"), math.nan)
        duration = _float(event.get("duration_sec"), math.nan)
        if not math.isfinite(start) or start < 0:
            errors.append(f"{path}.start_sec must be >= 0")
        if not math.isfinite(end) or end <= start:
            errors.append(f"{path}.end_sec must be greater than start_sec")
        if not math.isfinite(duration) or duration <= 0:
            errors.append(f"{path}.duration_sec must be > 0")
        elif math.isfinite(start) and math.isfinite(end) and abs(duration - (end - start)) > 0.001:
            errors.append(f"{path}.duration_sec does not match end_sec - start_sec")
        if math.isfinite(start) and start < previous_start:
            errors.append(f"{path} is not sorted by start_sec")
        previous_start = start

        severity = _int(event.get("severity"), -1)
        if not 0 <= severity <= 4:
            errors.append(f"{path}.severity must be in [0, 4]")
        confidence = _float(event.get("confidence"), -1.0)
        if not 0.0 <= confidence <= 1.0:
            errors.append(f"{path}.confidence must be in [0, 1]")
        source_type = str(event.get("source_type", "")).upper()
        if source_type not in SOURCE_TYPES:
            errors.append(f"{path}.source_type must be one of {sorted(SOURCE_TYPES)}")

        parameters = event.get("parameters")
        if not isinstance(parameters, dict):
            errors.append(f"{path}.parameters must be an object")
        else:
            for key in ("rate_mbit", "delay_ms", "jitter_ms", "loss_pct", "spike_ms"):
                value = _float(parameters.get(key), math.nan)
                if not math.isfinite(value) or value < 0:
                    errors.append(f"{path}.parameters.{key} must be >= 0")
            loss = _float(parameters.get("loss_pct"), math.nan)
            if math.isfinite(loss) and loss > 100:
                errors.append(f"{path}.parameters.loss_pct must be <= 100")
        if "directions" in event:
            _validate_direction_mapping(event.get("directions"), f"{path}.directions", errors)
    return errors


def load_document(path: Path, *, validate: bool = True) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    document = normalize_document(data)
    if validate:
        errors = validate_document(document)
        if errors:
            raise EventProfileError("Invalid event profile:\n- " + "\n- ".join(errors))
    return document


def save_document(path: Path, document: dict[str, Any], *, validate: bool = True) -> None:
    if validate:
        errors = validate_document(document)
        if errors:
            raise EventProfileError("Invalid event profile:\n- " + "\n- ".join(errors))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def legacy_rows(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [v1_event_to_legacy(event) for event in document.get("events", [])]


def update_from_legacy_rows(document: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    updated = copy.deepcopy(document)
    updated["events"] = [legacy_event_to_v1(row, i) for i, row in enumerate(rows, start=1)]
    return updated

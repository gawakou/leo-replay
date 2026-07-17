from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

CONDITION_FIELDS = (
    "delay_ms",
    "jitter_ms",
    "loss_pct",
    "rate_mbit",
    "reorder_pct",
    "correlation_pct",
)

_DIRECTION_ALIASES = {
    "forward": ("forward", "up", "uplink"),
    "reverse": ("reverse", "down", "downlink"),
}


class DirectionalProfileError(ValueError):
    """Raised when a directional replay profile is invalid."""


@dataclass(frozen=True)
class LinkCondition:
    delay_ms: float = 0.0
    jitter_ms: float = 0.0
    loss_pct: float = 0.0
    rate_mbit: float | None = None
    reorder_pct: float = 0.0
    correlation_pct: float = 0.0

    def validate(self, *, path: str = "condition") -> None:
        values = {
            "delay_ms": self.delay_ms,
            "jitter_ms": self.jitter_ms,
            "loss_pct": self.loss_pct,
            "reorder_pct": self.reorder_pct,
            "correlation_pct": self.correlation_pct,
        }
        if self.rate_mbit is not None:
            values["rate_mbit"] = self.rate_mbit
        for key, value in values.items():
            if not math.isfinite(value) or value < 0:
                raise DirectionalProfileError(f"{path}.{key} must be a finite value >= 0")
        for key in ("loss_pct", "reorder_pct", "correlation_pct"):
            if values[key] > 100:
                raise DirectionalProfileError(f"{path}.{key} must be <= 100")

    def to_mapping(self) -> dict[str, float | None]:
        return asdict(self)


@dataclass(frozen=True)
class DirectionalState:
    sec: float
    forward: LinkCondition
    reverse: LinkCondition
    note: str = ""

    def validate(self, *, path: str = "state") -> None:
        if not math.isfinite(self.sec) or self.sec < 0:
            raise DirectionalProfileError(f"{path}.sec must be a finite value >= 0")
        self.forward.validate(path=f"{path}.forward")
        self.reverse.validate(path=f"{path}.reverse")


@dataclass(frozen=True)
class ConversionPolicy:
    delay_policy: str = "split"
    delay_forward_share: float = 0.5
    jitter_policy: str = "split"
    loss_policy: str = "equivalent"
    rate_policy: str = "forward-only"
    reverse_default_rate_mbit: float | None = 260.0

    def validate(self) -> None:
        if self.delay_policy not in {"split", "mirror", "forward-only"}:
            raise DirectionalProfileError(f"unsupported delay policy: {self.delay_policy}")
        if self.jitter_policy not in {"split", "mirror", "forward-only"}:
            raise DirectionalProfileError(f"unsupported jitter policy: {self.jitter_policy}")
        if self.loss_policy not in {"equivalent", "mirror", "forward-only"}:
            raise DirectionalProfileError(f"unsupported loss policy: {self.loss_policy}")
        if self.rate_policy not in {"mirror", "forward-only"}:
            raise DirectionalProfileError(f"unsupported rate policy: {self.rate_policy}")
        if not 0.0 <= self.delay_forward_share <= 1.0:
            raise DirectionalProfileError("delay_forward_share must be in [0, 1]")
        if self.reverse_default_rate_mbit is not None and self.reverse_default_rate_mbit < 0:
            raise DirectionalProfileError("reverse_default_rate_mbit must be >= 0")


def _number(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise DirectionalProfileError(f"invalid numeric value: {value!r}") from exc
    if not math.isfinite(result):
        raise DirectionalProfileError(f"numeric value must be finite: {value!r}")
    return result


def _optional_number(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    return _number(value)


def _split_linear(value: float, policy: str, forward_share: float) -> tuple[float, float]:
    if policy == "mirror":
        return value, value
    if policy == "forward-only":
        return value, 0.0
    return value * forward_share, value * (1.0 - forward_share)


def _split_loss(loss_pct: float, policy: str, forward_share: float) -> tuple[float, float]:
    loss_pct = min(max(loss_pct, 0.0), 100.0)
    if policy == "mirror":
        return loss_pct, loss_pct
    if policy == "forward-only":
        return loss_pct, 0.0
    if loss_pct >= 100.0:
        return 100.0, 100.0
    survival = 1.0 - loss_pct / 100.0
    forward_loss = (1.0 - survival**forward_share) * 100.0
    reverse_loss = (1.0 - survival ** (1.0 - forward_share)) * 100.0
    return forward_loss, reverse_loss


def directionalize_condition(
    condition: LinkCondition,
    policy: ConversionPolicy,
) -> tuple[LinkCondition, LinkCondition]:
    policy.validate()
    condition.validate()
    forward_delay, reverse_delay = _split_linear(
        condition.delay_ms, policy.delay_policy, policy.delay_forward_share
    )
    forward_jitter, reverse_jitter = _split_linear(
        condition.jitter_ms, policy.jitter_policy, policy.delay_forward_share
    )
    forward_loss, reverse_loss = _split_loss(
        condition.loss_pct, policy.loss_policy, policy.delay_forward_share
    )
    if policy.rate_policy == "mirror":
        forward_rate = condition.rate_mbit
        reverse_rate = condition.rate_mbit
    else:
        forward_rate = condition.rate_mbit
        reverse_rate = policy.reverse_default_rate_mbit

    forward = LinkCondition(
        delay_ms=forward_delay,
        jitter_ms=forward_jitter,
        loss_pct=forward_loss,
        rate_mbit=forward_rate,
        reorder_pct=condition.reorder_pct,
        correlation_pct=condition.correlation_pct,
    )
    reverse = LinkCondition(
        delay_ms=reverse_delay,
        jitter_ms=reverse_jitter,
        loss_pct=reverse_loss,
        rate_mbit=reverse_rate,
        reorder_pct=0.0,
        correlation_pct=condition.correlation_pct,
    )
    forward.validate(path="forward")
    reverse.validate(path="reverse")
    return forward, reverse


def end_to_end_loss_pct(forward_loss_pct: float, reverse_loss_pct: float) -> float:
    forward_survival = 1.0 - min(max(forward_loss_pct, 0.0), 100.0) / 100.0
    reverse_survival = 1.0 - min(max(reverse_loss_pct, 0.0), 100.0) / 100.0
    return (1.0 - forward_survival * reverse_survival) * 100.0


def _direction_field(row: dict[str, Any], direction: str, field: str) -> Any:
    if "_" in field:
        stem, suffix = field.rsplit("_", 1)
    else:
        stem, suffix = field, ""
    for prefix in _DIRECTION_ALIASES[direction]:
        candidates = [f"{prefix}_{field}", f"{field}_{prefix}"]
        if suffix:
            candidates.append(f"{stem}_{prefix}_{suffix}")
        for candidate in candidates:
            value = row.get(candidate)
            if value not in (None, ""):
                return value
    return None


def _condition_from_directional_row(
    row: dict[str, Any],
    direction: str,
    *,
    default_rate_mbit: float | None,
) -> LinkCondition | None:
    values = {field: _direction_field(row, direction, field) for field in CONDITION_FIELDS}
    if not any(value not in (None, "") for value in values.values()):
        return None
    condition = LinkCondition(
        delay_ms=_number(values["delay_ms"], 0.0),
        jitter_ms=_number(values["jitter_ms"], 0.0),
        loss_pct=_number(values["loss_pct"], 0.0),
        rate_mbit=_optional_number(values["rate_mbit"], default_rate_mbit),
        reorder_pct=_number(values["reorder_pct"], 0.0),
        correlation_pct=_number(values["correlation_pct"], 0.0),
    )
    condition.validate(path=direction)
    return condition


def _legacy_condition(row: dict[str, Any], default_rate_mbit: float | None) -> LinkCondition:
    condition = LinkCondition(
        delay_ms=_number(row.get("delay_ms"), 0.0),
        jitter_ms=_number(row.get("jitter_ms"), 0.0),
        loss_pct=_number(row.get("loss_pct"), 0.0),
        rate_mbit=_optional_number(row.get("rate_mbit"), default_rate_mbit),
        reorder_pct=_number(row.get("reorder_pct"), 0.0),
        correlation_pct=_number(row.get("correlation_pct"), 0.0),
    )
    condition.validate(path="legacy")
    return condition


def row_to_directional_state(
    row: dict[str, Any],
    *,
    policy: ConversionPolicy,
    default_rate_mbit: float | None = None,
) -> DirectionalState:
    sec = _number(row.get("sec"), 0.0)
    forward = _condition_from_directional_row(
        row, "forward", default_rate_mbit=default_rate_mbit
    )
    reverse = _condition_from_directional_row(
        row,
        "reverse",
        default_rate_mbit=policy.reverse_default_rate_mbit,
    )
    if forward is None and reverse is None:
        forward, reverse = directionalize_condition(
            _legacy_condition(row, default_rate_mbit), policy
        )
    elif forward is None or reverse is None:
        raise DirectionalProfileError(
            "directional CSV rows must define both forward and reverse conditions"
        )
    state = DirectionalState(
        sec=sec,
        forward=forward,
        reverse=reverse,
        note=str(row.get("note", "") or "").strip(),
    )
    state.validate()
    return state


def read_directional_csv(
    path: Path,
    *,
    policy: ConversionPolicy | None = None,
    default_rate_mbit: float | None = None,
) -> list[DirectionalState]:
    policy = policy or ConversionPolicy()
    policy.validate()
    states: list[DirectionalState] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if "sec" not in (reader.fieldnames or []):
            raise DirectionalProfileError("CSV is missing required column: sec")
        for line_number, row in enumerate(reader, start=2):
            try:
                states.append(
                    row_to_directional_state(
                        row,
                        policy=policy,
                        default_rate_mbit=default_rate_mbit,
                    )
                )
            except DirectionalProfileError as exc:
                raise DirectionalProfileError(f"CSV line {line_number}: {exc}") from exc
    if not states:
        raise DirectionalProfileError("CSV profile is empty")
    states.sort(key=lambda state: state.sec)
    return states


def write_directional_csv(path: Path, states: Iterable[DirectionalState]) -> None:
    fieldnames = ["sec"]
    for direction in ("forward", "reverse"):
        fieldnames.extend(f"{direction}_{field}" for field in CONDITION_FIELDS)
    fieldnames.append("note")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for state in states:
            state.validate()
            row: dict[str, Any] = {"sec": state.sec, "note": state.note}
            for direction in ("forward", "reverse"):
                condition = getattr(state, direction)
                for field, value in condition.to_mapping().items():
                    row[f"{direction}_{field}"] = "" if value is None else value
            writer.writerow(row)


def condition_from_mapping(mapping: dict[str, Any], *, default_rate: float | None = None) -> LinkCondition:
    condition = LinkCondition(
        delay_ms=_number(mapping.get("delay_ms"), 0.0),
        jitter_ms=_number(mapping.get("jitter_ms"), 0.0),
        loss_pct=_number(mapping.get("loss_pct"), 0.0),
        rate_mbit=_optional_number(mapping.get("rate_mbit"), default_rate),
        reorder_pct=_number(mapping.get("reorder_pct"), 0.0),
        correlation_pct=_number(mapping.get("correlation_pct"), 0.0),
    )
    condition.validate()
    return condition


def _event_condition_mapping(condition: LinkCondition) -> dict[str, Any]:
    mapping = condition.to_mapping()
    if mapping["rate_mbit"] is None:
        mapping["rate_mbit"] = 0.0
    return mapping


def _direction_mapping(forward: LinkCondition, reverse: LinkCondition) -> dict[str, Any]:
    return {
        "forward": _event_condition_mapping(forward),
        "reverse": _event_condition_mapping(reverse),
    }


def directionalize_event_document(
    document: dict[str, Any],
    *,
    policy: ConversionPolicy,
) -> dict[str, Any]:
    import copy

    policy.validate()
    updated = copy.deepcopy(document)
    baseline = updated.setdefault("baseline", {})
    baseline_condition = condition_from_mapping(baseline)
    baseline_forward, baseline_reverse = directionalize_condition(baseline_condition, policy)
    baseline["directions"] = _direction_mapping(baseline_forward, baseline_reverse)

    for event in updated.get("events", []):
        parameters = event.setdefault("parameters", {})
        condition = condition_from_mapping(parameters)
        spike_ms = _number(parameters.get("spike_ms"), 0.0)
        if spike_ms > 0:
            condition = LinkCondition(
                delay_ms=condition.delay_ms + spike_ms,
                jitter_ms=condition.jitter_ms,
                loss_pct=condition.loss_pct,
                rate_mbit=condition.rate_mbit,
                reorder_pct=condition.reorder_pct,
                correlation_pct=condition.correlation_pct,
            )
        forward, reverse = directionalize_condition(condition, policy)
        event["directions"] = _direction_mapping(forward, reverse)

    metadata = updated.setdefault("metadata", {})
    metadata["directionalization"] = {
        "delay_policy": policy.delay_policy,
        "delay_forward_share": policy.delay_forward_share,
        "jitter_policy": policy.jitter_policy,
        "loss_policy": policy.loss_policy,
        "rate_policy": policy.rate_policy,
        "reverse_default_rate_mbit": policy.reverse_default_rate_mbit,
    }
    return updated


def event_direction_conditions(
    container: dict[str, Any],
    *,
    policy: ConversionPolicy,
) -> tuple[LinkCondition, LinkCondition]:
    directions = container.get("directions")
    if isinstance(directions, dict):
        forward_mapping = directions.get("forward")
        reverse_mapping = directions.get("reverse")
        if not isinstance(forward_mapping, dict) or not isinstance(reverse_mapping, dict):
            raise DirectionalProfileError(
                "directions must contain forward and reverse objects"
            )
        return condition_from_mapping(forward_mapping), condition_from_mapping(reverse_mapping)
    scalar_mapping = container.get("parameters")
    if not isinstance(scalar_mapping, dict):
        scalar_mapping = container
    condition = condition_from_mapping(scalar_mapping)
    spike_ms = _number(scalar_mapping.get("spike_ms"), 0.0)
    if spike_ms > 0:
        condition = LinkCondition(
            delay_ms=condition.delay_ms + spike_ms,
            jitter_ms=condition.jitter_ms,
            loss_pct=condition.loss_pct,
            rate_mbit=condition.rate_mbit,
            reorder_pct=condition.reorder_pct,
            correlation_pct=condition.correlation_pct,
        )
    return directionalize_condition(condition, policy)


def write_conversion_metadata(
    path: Path,
    *,
    input_path: Path,
    output_path: Path,
    mode: str,
    policy: ConversionPolicy,
    states: int | None = None,
    events: int | None = None,
) -> None:
    payload = {
        "input": str(input_path),
        "output": str(output_path),
        "mode": mode,
        "policy": asdict(policy),
    }
    if states is not None:
        payload["states"] = states
    if events is not None:
        payload["events"] = events
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

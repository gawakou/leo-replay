from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from skyfield.api import wgs84

from .catalog import OrbitCatalog, timescale
from .models import ObserverSite, iso_utc, parse_utc, sha256_file, utc_now_iso


VISIBILITY_FIELDS = [
    "timestamp_utc",
    "site_id",
    "satellite_name",
    "norad_cat_id",
    "object_id",
    "elevation_deg",
    "azimuth_deg",
    "slant_range_km",
    "visible",
    "element_epoch_utc",
    "epoch_distance_sec",
    "stale_element",
    "propagation_error",
]


@dataclass(frozen=True)
class VisibilityResult:
    rows: tuple[dict[str, Any], ...]
    metadata: dict[str, Any]


def sample_datetimes(start: datetime, duration_sec: float, step_sec: float) -> list[datetime]:
    if duration_sec < 0:
        raise ValueError("duration_sec must be >= 0")
    if step_sec <= 0:
        raise ValueError("step_sec must be > 0")
    count = int(math.floor(duration_sec / step_sec)) + 1
    values = [start + timedelta(seconds=index * step_sec) for index in range(count)]
    final = start + timedelta(seconds=duration_sec)
    if values[-1] < final:
        values.append(final)
    return values


def compute_visibility(
    catalog: OrbitCatalog,
    site: ObserverSite,
    *,
    start_utc: str,
    duration_sec: float,
    step_sec: float,
    minimum_elevation_deg: float = 25.0,
    only_visible: bool = True,
    stale_after_days: float = 14.0,
) -> VisibilityResult:
    site.validate()
    if not -90.0 <= minimum_elevation_deg <= 90.0:
        raise ValueError("minimum_elevation_deg must be between -90 and 90")
    if stale_after_days < 0:
        raise ValueError("stale_after_days must be >= 0")

    start = parse_utc(start_utc)
    datetimes = sample_datetimes(start, duration_sec, step_sec)
    ts = timescale()
    skyfield_times = ts.from_datetimes(datetimes)
    observer = wgs84.latlon(
        site.latitude_deg,
        site.longitude_deg,
        elevation_m=site.elevation_m,
    )

    rows: list[dict[str, Any]] = []
    visible_counts = {iso_utc(value): 0 for value in datetimes}
    stale_rows = 0
    propagation_errors = 0

    for record in catalog.satellites:
        epoch = parse_utc(record.epoch_utc)
        topocentric = (record.satellite - observer).at(skyfield_times)
        altitude, azimuth, distance = topocentric.altaz()
        altitudes = list(altitude.degrees)
        azimuths = list(azimuth.degrees)
        distances = list(distance.km)
        messages = topocentric.message
        if messages is None:
            messages = [None] * len(datetimes)
        elif isinstance(messages, str):
            messages = [messages] * len(datetimes)
        else:
            messages = list(messages)

        for moment, elevation, azimuth_deg, range_km, message in zip(
            datetimes, altitudes, azimuths, distances, messages
        ):
            finite = all(math.isfinite(float(value)) for value in (elevation, azimuth_deg, range_km))
            error = str(message) if message else None
            if not finite and not error:
                error = "non-finite propagation result"
            if error:
                propagation_errors += 1
            visible = finite and not error and float(elevation) >= minimum_elevation_deg
            timestamp = iso_utc(moment)
            if visible:
                visible_counts[timestamp] += 1
            if only_visible and not visible:
                continue
            epoch_distance_sec = abs((moment - epoch).total_seconds())
            stale = epoch_distance_sec > stale_after_days * 86400.0
            if stale:
                stale_rows += 1
            rows.append(
                {
                    "timestamp_utc": timestamp,
                    "site_id": site.site_id,
                    "satellite_name": record.name,
                    "norad_cat_id": record.norad_cat_id,
                    "object_id": record.object_id or "",
                    "elevation_deg": round(float(elevation), 6) if finite else "",
                    "azimuth_deg": round(float(azimuth_deg) % 360.0, 6) if finite else "",
                    "slant_range_km": round(float(range_km), 6) if finite else "",
                    "visible": visible,
                    "element_epoch_utc": record.epoch_utc,
                    "epoch_distance_sec": round(epoch_distance_sec, 6),
                    "stale_element": stale,
                    "propagation_error": error or "",
                }
            )

    metadata = {
        "schema_version": "1.0",
        "profile_type": "visibility",
        "generated_at_utc": utc_now_iso(),
        "source_file": catalog.source_path.name,
        "source_format": catalog.source_format,
        "source_sha256": sha256_file(catalog.source_path),
        "element_epoch_min_utc": min(record.epoch_utc for record in catalog.satellites),
        "element_epoch_max_utc": max(record.epoch_utc for record in catalog.satellites),
        "site": site.to_dict(),
        "start_utc": iso_utc(start),
        "duration_sec": duration_sec,
        "step_sec": step_sec,
        "sample_count": len(datetimes),
        "satellite_count": len(catalog.satellites),
        "minimum_elevation_deg": minimum_elevation_deg,
        "only_visible": only_visible,
        "row_count": len(rows),
        "visible_counts": [
            {"timestamp_utc": timestamp, "visible_count": count}
            for timestamp, count in visible_counts.items()
        ],
        "stale_after_days": stale_after_days,
        "stale_row_count": stale_rows,
        "propagation_error_count": propagation_errors,
    }
    return VisibilityResult(tuple(rows), metadata)


def write_visibility_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=VISIBILITY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

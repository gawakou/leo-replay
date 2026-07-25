from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from leo_replay import __version__

from .catalog import OrbitCatalog
from .models import iso_utc, parse_utc, sha256_file, utc_now_iso


def create_source_manifest(
    catalog: OrbitCatalog,
    *,
    source_name: str | None = None,
    source_uri: str | None = None,
    retrieved_at_utc: str | None = None,
) -> dict[str, Any]:
    epochs = sorted(parse_utc(record.epoch_utc) for record in catalog.satellites)
    return {
        "schema_version": "1.0",
        "manifest_type": "orbit_source",
        "generated_at_utc": utc_now_iso(),
        "generator": f"leo-replay {__version__}",
        "source": {
            "name": source_name,
            "uri": source_uri,
            "retrieved_at_utc": iso_utc(parse_utc(retrieved_at_utc)) if retrieved_at_utc else None,
            "local_file": catalog.source_path.name,
            "format": catalog.source_format,
            "sha256": sha256_file(catalog.source_path),
        },
        "satellite_count": len(catalog.satellites),
        "element_epoch_min_utc": iso_utc(epochs[0]),
        "element_epoch_max_utc": iso_utc(epochs[-1]),
        "satellites": [
            {
                "name": record.name,
                "norad_cat_id": record.norad_cat_id,
                "object_id": record.object_id,
                "element_epoch_utc": record.epoch_utc,
            }
            for record in catalog.satellites
        ],
    }


def save_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

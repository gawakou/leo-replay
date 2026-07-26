"""Orbit context, visibility candidates, and event annotation."""

from .acquisition import (
    OrbitAcquisitionError,
    fetch_celestrak_snapshot,
    fetch_space_track_snapshot,
)
from .annotation import annotate_event_document, load_visibility_rows
from .catalog import OrbitCatalog, OrbitSatellite, load_catalog
from .models import ObserverSite, OrbitDataError
from .provenance import create_source_manifest
from .snapshot import OrbitSnapshotError, verify_snapshot
from .visibility import VisibilityResult, compute_visibility, write_visibility_csv

__all__ = [
    "OrbitAcquisitionError",
    "OrbitCatalog",
    "OrbitDataError",
    "OrbitSatellite",
    "OrbitSnapshotError",
    "ObserverSite",
    "VisibilityResult",
    "annotate_event_document",
    "compute_visibility",
    "fetch_celestrak_snapshot",
    "fetch_space_track_snapshot",
    "create_source_manifest",
    "load_catalog",
    "load_visibility_rows",
    "verify_snapshot",
    "write_visibility_csv",
]

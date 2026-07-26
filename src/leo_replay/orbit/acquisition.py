from __future__ import annotations

import http.cookiejar
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from leo_replay import __version__

from .models import OrbitDataError, parse_utc, utc_now_iso
from .snapshot import (
    SnapshotPart,
    SnapshotWriteResult,
    existing_snapshot_matches,
    load_manifest,
    snapshot_age_seconds,
    verify_snapshot,
    write_snapshot,
)


class OrbitAcquisitionError(OrbitDataError):
    """Raised when an orbit data provider request fails."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes
    final_url: str


class HttpTransport:
    """Small urllib-based HTTP session with cookie support and no automatic retries."""

    def __init__(self, *, timeout_sec: float = 30.0, user_agent: str | None = None):
        if timeout_sec <= 0:
            raise OrbitAcquisitionError("timeout_sec must be > 0")
        self.timeout_sec = timeout_sec
        self.user_agent = user_agent or f"leo-replay/{__version__} orbit-snapshot"
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar))

    def get(self, url: str) -> HttpResponse:
        request = urllib.request.Request(url, method="GET", headers={"User-Agent": self.user_agent})
        return self._open(request)

    def post_form(self, url: str, form: Mapping[str, str]) -> HttpResponse:
        data = urllib.parse.urlencode(dict(form)).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "User-Agent": self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        return self._open(request)

    def _open(self, request: urllib.request.Request) -> HttpResponse:
        try:
            with self.opener.open(request, timeout=self.timeout_sec) as response:
                return HttpResponse(
                    status=int(response.status),
                    headers={key: value for key, value in response.headers.items()},
                    body=response.read(),
                    final_url=response.geturl(),
                )
        except urllib.error.HTTPError as exc:
            body = exc.read()
            detail = ""
            if request.get_method() == "GET":
                message = body.decode("utf-8", errors="replace")[:500].strip()
                detail = f": {message}" if message else ""
            raise OrbitAcquisitionError(
                f"HTTP {exc.code} from {request.full_url}; no retry was attempted{detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise OrbitAcquisitionError(f"failed to access {request.full_url}: {exc.reason}") from exc


CELESTRAK_BASE_URL = "https://celestrak.org/NORAD/elements/gp.php"
CELESTRAK_MINIMUM_REFRESH_SEC = 2 * 60 * 60
SPACE_TRACK_BASE_URL = "https://www.space-track.org"
SPACE_TRACK_MAX_IDS_PER_REQUEST = 200


def _clean_format(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"json", "csv", "tle"}:
        raise OrbitAcquisitionError("format must be json, csv, or tle")
    return normalized


def build_celestrak_request(
    *,
    query_type: str,
    query_value: str,
    output_format: str,
    base_url: str = CELESTRAK_BASE_URL,
) -> tuple[str, dict[str, Any]]:
    query_name = query_type.strip().upper()
    if query_name not in {"CATNR", "INTDES", "GROUP", "NAME", "SPECIAL"}:
        raise OrbitAcquisitionError("unsupported CelesTrak query type")
    value = query_value.strip()
    if not value:
        raise OrbitAcquisitionError("CelesTrak query value must not be empty")
    output_format = _clean_format(output_format)
    params = {query_name: value, "FORMAT": output_format.upper()}
    url = base_url.rstrip("?") + "?" + urllib.parse.urlencode(params)
    request = {
        "provider": "celestrak",
        "method": "GET",
        "endpoint": base_url,
        "query": {query_name: value},
        "format": output_format,
        "source_uri": url,
    }
    return url, request


def fetch_celestrak_snapshot(
    *,
    output_dir: Path,
    query_type: str,
    query_value: str,
    output_format: str = "json",
    force: bool = False,
    override_refresh_policy: bool = False,
    timeout_sec: float = 30.0,
    base_url: str = CELESTRAK_BASE_URL,
    transport: HttpTransport | None = None,
) -> SnapshotWriteResult:
    url, request = build_celestrak_request(
        query_type=query_type,
        query_value=query_value,
        output_format=output_format,
        base_url=base_url,
    )
    output_dir = output_dir.resolve()
    if output_dir.exists() and existing_snapshot_matches(output_dir, request):
        if not force:
            manifest = load_manifest(output_dir)
            verify_snapshot(output_dir)
            return SnapshotWriteResult(output_dir=output_dir, manifest=manifest, reused=True)
        age = snapshot_age_seconds(output_dir)
        if age < CELESTRAK_MINIMUM_REFRESH_SEC and not override_refresh_policy:
            remaining = CELESTRAK_MINIMUM_REFRESH_SEC - age
            raise OrbitAcquisitionError(
                "CelesTrak GP snapshots must not be refreshed more often than every 2 hours; "
                f"wait about {remaining:.0f} seconds or use --override-refresh-policy explicitly"
            )
    elif output_dir.exists() and not force:
        raise OrbitAcquisitionError(
            f"snapshot directory exists with a different request: {output_dir}; use a new directory"
        )

    client = transport or HttpTransport(timeout_sec=timeout_sec)
    response = client.get(url)
    if response.status != 200:
        raise OrbitAcquisitionError(f"unexpected CelesTrak HTTP status: {response.status}")
    part = SnapshotPart(
        body=response.body,
        headers=response.headers,
        source_uri=response.final_url,
        status=response.status,
    )
    return write_snapshot(
        output_dir,
        provider="celestrak",
        request=request,
        output_format=_clean_format(output_format),
        parts=[part],
        force=force,
        metadata={
            "usage_policy": "Do not download the same GP data more than once per 2-hour update.",
            "minimum_refresh_sec": CELESTRAK_MINIMUM_REFRESH_SEC,
        },
    )


def read_norad_ids(values: Iterable[str], file_path: Path | None = None) -> list[str]:
    raw = list(values)
    if file_path is not None:
        if not file_path.is_file():
            raise FileNotFoundError(file_path)
        raw.extend(file_path.read_text(encoding="utf-8").splitlines())
    result: list[str] = []
    for item in raw:
        for token in re.split(r"[\s,]+", item.strip()):
            if not token:
                continue
            if not token.isdigit() or not 1 <= len(token) <= 9:
                raise OrbitAcquisitionError(f"invalid NORAD catalog ID: {token}")
            normalized = str(int(token))
            if normalized not in result:
                result.append(normalized)
    if not result:
        raise OrbitAcquisitionError("at least one NORAD catalog ID is required")
    return result


def _space_track_interval(start: str, stop: str) -> str:
    start_utc = parse_utc(start)
    stop_utc = parse_utc(stop)
    if stop_utc <= start_utc:
        raise OrbitAcquisitionError("Space-Track --stop must be later than --start")
    start_text = start_utc.isoformat(timespec="seconds").replace("+00:00", "Z")
    stop_text = stop_utc.isoformat(timespec="seconds").replace("+00:00", "Z")
    return f"{start_text}--{stop_text}"


def _path_value(value: str) -> str:
    return urllib.parse.quote(value, safe=",-_.:TZ")


def build_space_track_query_urls(
    *,
    query_class: str,
    norad_ids: Iterable[str],
    output_format: str,
    start: str | None = None,
    stop: str | None = None,
    batch_size: int = 100,
    base_url: str = SPACE_TRACK_BASE_URL,
) -> tuple[list[str], dict[str, Any]]:
    query_class = query_class.strip().lower()
    if query_class not in {"gp", "gp_history"}:
        raise OrbitAcquisitionError("Space-Track class must be gp or gp_history")
    output_format = _clean_format(output_format)
    ids = read_norad_ids(norad_ids)
    if not 1 <= batch_size <= SPACE_TRACK_MAX_IDS_PER_REQUEST:
        raise OrbitAcquisitionError(
            f"batch_size must be between 1 and {SPACE_TRACK_MAX_IDS_PER_REQUEST}"
        )
    interval = None
    if query_class == "gp_history":
        if not start or not stop:
            raise OrbitAcquisitionError("gp_history requires --start and --stop")
        interval = _space_track_interval(start, stop)
    elif start or stop:
        raise OrbitAcquisitionError("--start and --stop are only valid for gp_history")

    base = base_url.rstrip("/")
    urls = []
    for offset in range(0, len(ids), batch_size):
        batch = ids[offset : offset + batch_size]
        segments = [
            "basicspacedata",
            "query",
            "class",
            query_class,
            "NORAD_CAT_ID",
            ",".join(batch),
        ]
        if interval is not None:
            segments.extend(["EPOCH", interval])
        order = "NORAD_CAT_ID,EPOCH" if query_class == "gp_history" else "NORAD_CAT_ID"
        segments.extend(["orderby", order, "format", output_format, "emptyresult", "show"])
        urls.append(base + "/" + "/".join(_path_value(segment) for segment in segments))

    request = {
        "provider": "space-track",
        "method": "POST login, then GET query",
        "base_url": base,
        "class": query_class,
        "norad_cat_ids": ids,
        "norad_id_count": len(ids),
        "epoch_start_utc": parse_utc(start).isoformat().replace("+00:00", "Z") if start else None,
        "epoch_stop_utc": parse_utc(stop).isoformat().replace("+00:00", "Z") if stop else None,
        "format": output_format,
        "batch_size": batch_size,
        "query_urls": urls,
    }
    return urls, request


def _space_track_credentials(identity_env: str, password_env: str) -> tuple[str, str]:
    identity = os.environ.get(identity_env, "").strip()
    password = os.environ.get(password_env, "")
    if not identity or not password:
        raise OrbitAcquisitionError(
            f"Space-Track credentials are required in {identity_env} and {password_env}"
        )
    return identity, password


def fetch_space_track_snapshot(
    *,
    output_dir: Path,
    query_class: str,
    norad_ids: Iterable[str],
    output_format: str = "json",
    start: str | None = None,
    stop: str | None = None,
    batch_size: int = 100,
    norad_id_file: Path | None = None,
    identity_env: str = "SPACETRACK_IDENTITY",
    password_env: str = "SPACETRACK_PASSWORD",
    force: bool = False,
    timeout_sec: float = 60.0,
    base_url: str = SPACE_TRACK_BASE_URL,
    transport: HttpTransport | None = None,
) -> SnapshotWriteResult:
    ids = read_norad_ids(norad_ids, norad_id_file)
    urls, request = build_space_track_query_urls(
        query_class=query_class,
        norad_ids=ids,
        output_format=output_format,
        start=start,
        stop=stop,
        batch_size=batch_size,
        base_url=base_url,
    )
    request["credential_source"] = {
        "identity_env": identity_env,
        "password_env": password_env,
        "credential_values_stored": False,
    }
    output_dir = output_dir.resolve()
    if output_dir.exists() and existing_snapshot_matches(output_dir, request):
        if not force:
            manifest = load_manifest(output_dir)
            verify_snapshot(output_dir)
            return SnapshotWriteResult(output_dir=output_dir, manifest=manifest, reused=True)
    elif output_dir.exists() and not force:
        raise OrbitAcquisitionError(
            f"snapshot directory exists with a different request: {output_dir}; use a new directory"
        )

    identity, password = _space_track_credentials(identity_env, password_env)
    client = transport or HttpTransport(timeout_sec=timeout_sec)
    login_url = base_url.rstrip("/") + "/ajaxauth/login"
    login = client.post_form(login_url, {"identity": identity, "password": password})
    if login.status != 200:
        raise OrbitAcquisitionError(f"Space-Track login returned HTTP {login.status}")

    parts = []
    for url in urls:
        response = client.get(url)
        if response.status != 200:
            raise OrbitAcquisitionError(f"Space-Track query returned HTTP {response.status}")
        parts.append(
            SnapshotPart(
                body=response.body,
                headers=response.headers,
                source_uri=response.final_url,
                status=response.status,
            )
        )
    return write_snapshot(
        output_dir,
        provider="space-track",
        request=request,
        output_format=_clean_format(output_format),
        parts=parts,
        force=force,
        metadata={
            "authenticated": True,
            "credential_values_stored": False,
            "acquired_at_utc": utc_now_iso(),
        },
    )

from __future__ import annotations

import json
from pathlib import Path

import pytest

from leo_replay.orbit.acquisition import (
    CELESTRAK_MINIMUM_REFRESH_SEC,
    HttpResponse,
    OrbitAcquisitionError,
    build_celestrak_request,
    build_space_track_query_urls,
    fetch_celestrak_snapshot,
    fetch_space_track_snapshot,
    read_norad_ids,
)
from leo_replay.orbit.snapshot import verify_snapshot

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/orbit/iss-omm.example.json"


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.get_calls = []
        self.post_calls = []

    def get(self, url):
        self.get_calls.append(url)
        if not self.responses:
            raise AssertionError("unexpected GET")
        body = self.responses.pop(0)
        return HttpResponse(
            200,
            {"Content-Type": "application/json", "Set-Cookie": "session=secret-session"},
            body,
            url,
        )

    def post_form(self, url, form):
        self.post_calls.append((url, dict(form)))
        return HttpResponse(200, {"Set-Cookie": "session=fake"}, b"ok", url)


def record(cat_id, name):
    value = json.loads(EXAMPLE.read_text(encoding="utf-8"))[0]
    value["NORAD_CAT_ID"] = cat_id
    value["OBJECT_NAME"] = name
    return value


def test_build_celestrak_request_uses_documented_query_shape():
    url, request = build_celestrak_request(
        query_type="group",
        query_value="STARLINK",
        output_format="json",
    )
    assert "gp.php?" in url
    assert "GROUP=STARLINK" in url
    assert "FORMAT=JSON" in url
    assert request["query"] == {"GROUP": "STARLINK"}


def test_celestrak_fetch_is_immutable_and_reused(tmp_path):
    output = tmp_path / "celestrak"
    transport = FakeTransport([EXAMPLE.read_bytes()])
    first = fetch_celestrak_snapshot(
        output_dir=output,
        query_type="catnr",
        query_value="25544",
        transport=transport,
    )
    assert first.reused is False
    assert len(transport.get_calls) == 1
    assert verify_snapshot(output)["record_count"] == 1

    no_network = FakeTransport([])
    second = fetch_celestrak_snapshot(
        output_dir=output,
        query_type="catnr",
        query_value="25544",
        transport=no_network,
    )
    assert second.reused is True
    assert not no_network.get_calls

    with pytest.raises(OrbitAcquisitionError, match="2 hours"):
        fetch_celestrak_snapshot(
            output_dir=output,
            query_type="catnr",
            query_value="25544",
            force=True,
            transport=FakeTransport([EXAMPLE.read_bytes()]),
        )
    assert CELESTRAK_MINIMUM_REFRESH_SEC == 7200


def test_space_track_query_batches_ids_and_preserves_epoch_range():
    ids = [str(10000 + index) for index in range(205)]
    urls, request = build_space_track_query_urls(
        query_class="gp_history",
        norad_ids=ids,
        output_format="json",
        start="2026-07-01T00:00:00Z",
        stop="2026-07-01T01:00:00Z",
        batch_size=100,
    )
    assert len(urls) == 3
    assert "/class/gp_history/" in urls[0]
    assert "/EPOCH/2026-07-01T00:00:00Z--2026-07-01T01:00:00Z/" in urls[0]
    assert request["norad_id_count"] == 205
    assert request["batch_size"] == 100


def test_space_track_fetch_merges_parts_without_storing_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("SPACETRACK_IDENTITY", "researcher@example.invalid")
    monkeypatch.setenv("SPACETRACK_PASSWORD", "do-not-store-this")
    part1 = (json.dumps([record(25544, "ISS")]) + "\n").encode()
    part2 = (json.dumps([record(43013, "STARLINK-TEST")]) + "\n").encode()
    transport = FakeTransport([part1, part2])
    output = tmp_path / "space-track"
    result = fetch_space_track_snapshot(
        output_dir=output,
        query_class="gp_history",
        norad_ids=["25544", "43013"],
        output_format="json",
        start="2026-07-01T00:00:00Z",
        stop="2026-07-01T01:00:00Z",
        batch_size=1,
        transport=transport,
    )
    assert result.manifest["record_count"] == 2
    assert result.manifest["part_count"] == 2
    assert len(transport.post_calls) == 1
    assert len(transport.get_calls) == 2
    assert verify_snapshot(output)["record_count"] == 2
    serialized = (output / "request.json").read_text(encoding="utf-8")
    manifest_text = (output / "manifest.json").read_text(encoding="utf-8")
    assert "do-not-store-this" not in serialized + manifest_text
    assert "researcher@example.invalid" not in serialized + manifest_text
    assert "credential_values_stored" in serialized
    headers_text = "".join(
        path.read_text(encoding="utf-8")
        for path in sorted((output / "raw").glob("*.headers.json"))
    )
    assert "secret-session" not in headers_text
    assert "Set-Cookie" not in headers_text


def test_space_track_requires_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("SPACETRACK_IDENTITY", raising=False)
    monkeypatch.delenv("SPACETRACK_PASSWORD", raising=False)
    with pytest.raises(OrbitAcquisitionError, match="credentials are required"):
        fetch_space_track_snapshot(
            output_dir=tmp_path / "missing",
            query_class="gp",
            norad_ids=["25544"],
            transport=FakeTransport([]),
        )


def test_norad_id_reader_deduplicates_and_validates(tmp_path):
    path = tmp_path / "ids.txt"
    path.write_text("25544\n43013,25544\n", encoding="utf-8")
    assert read_norad_ids(["100001"], path) == ["100001", "25544", "43013"]
    with pytest.raises(OrbitAcquisitionError, match="invalid NORAD"):
        read_norad_ids(["STARLINK"])


def test_space_track_http_session_uses_login_cookie(tmp_path, monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    payload = EXAMPLE.read_bytes()
    observed = {"login": False, "cookie": None}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            observed["login"] = self.path == "/ajaxauth/login"
            self.send_response(200)
            self.send_header("Set-Cookie", "session=local-test; Path=/")
            self.end_headers()
            self.wfile.write(b"ok")

        def do_GET(self):
            observed["cookie"] = self.headers.get("Cookie")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Set-Cookie", "rotation=do-not-store; Path=/")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv("SPACETRACK_IDENTITY", "local@example.invalid")
        monkeypatch.setenv("SPACETRACK_PASSWORD", "local-password")
        output = tmp_path / "http-session"
        result = fetch_space_track_snapshot(
            output_dir=output,
            query_class="gp",
            norad_ids=["25544"],
            base_url=f"http://127.0.0.1:{server.server_port}",
        )
        assert result.manifest["record_count"] == 1
        assert observed["login"] is True
        assert observed["cookie"] == "session=local-test"
        headers = (output / "raw/part-0001.headers.json").read_text(encoding="utf-8")
        assert "rotation=do-not-store" not in headers
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

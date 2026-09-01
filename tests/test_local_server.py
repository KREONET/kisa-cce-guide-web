"""Tests for the local static-site server."""

from __future__ import annotations

import argparse
import threading
from http import HTTPStatus
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from conversion import serve_site
from conversion.paths import BUILD_DIRECTORY
from conversion.serve_site import create_local_server, normalize_base_path


def test_normalize_base_path() -> None:
    """Valid hosting prefixes must normalize to one leading slash."""

    assert normalize_base_path("") == ""
    assert normalize_base_path("/") == ""
    assert normalize_base_path("kisa-cce-guide-web/") == "/kisa-cce-guide-web"
    with pytest.raises(argparse.ArgumentTypeError, match="invalid base path"):
        normalize_base_path("/../private")


def test_no_build_reports_the_artifact_site_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The no-build failure must identify the shared generated-site location."""

    monkeypatch.setattr(serve_site, "repository_root", lambda: tmp_path)
    monkeypatch.setattr(
        serve_site.sys,
        "argv",
        ["serve-site", "--no-build", "--log-directory", str(tmp_path / "logs")],
    )

    assert serve_site.main() == 1

    captured = capsys.readouterr()
    expected_site_path = (BUILD_DIRECTORY / "site" / "index.html").as_posix()
    assert f"{expected_site_path} is missing" in captured.err


def test_local_server_serves_root_and_custom_404(tmp_path: Path) -> None:
    """The server must resolve a configured prefix and preserve 404 status."""

    site_directory = tmp_path / "site"
    site_directory.mkdir()
    (site_directory / "index.html").write_text("<h1>Local guide</h1>", encoding="utf-8")
    (site_directory / "404.html").write_text("<h1>Missing guide</h1>", encoding="utf-8")
    server = create_local_server(
        site_directory=site_directory,
        host="127.0.0.1",
        port=0,
        base_path="/kisa-cce-guide-web",
    )
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    port = int(server.server_address[1])
    try:
        with urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
            assert response.status == HTTPStatus.OK
            assert response.geturl().endswith("/kisa-cce-guide-web/")
            assert b"Local guide" in response.read()
        with pytest.raises(HTTPError) as error:
            urlopen(
                f"http://127.0.0.1:{port}/kisa-cce-guide-web/missing",
                timeout=5,
            )
        assert error.value.code == HTTPStatus.NOT_FOUND
        assert b"Missing guide" in error.value.read()
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)

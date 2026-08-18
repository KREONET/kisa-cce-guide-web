"""Build and serve the generated guide on a local HTTP server."""

from __future__ import annotations

import argparse
import re
import socket
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import BaseServer
from urllib.parse import urlsplit, urlunsplit

from conversion.build_content import build
from conversion.common import repository_root

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
BASE_PATH_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9._~-]+$")


def normalize_base_path(value: str) -> str:
    """Normalize and validate an optional local URL path prefix."""

    stripped_value = value.strip()
    if not stripped_value or stripped_value == "/":
        return ""
    segments = [segment for segment in stripped_value.split("/") if segment]
    if not segments or any(
        segment in {".", ".."} or BASE_PATH_SEGMENT_PATTERN.fullmatch(segment) is None
        for segment in segments
    ):
        msg = f"invalid base path: {value!r}"
        raise argparse.ArgumentTypeError(msg)
    return "/" + "/".join(segments)


def _request_handler_type(
    *,
    site_directory: Path,
    base_path: str,
) -> type[SimpleHTTPRequestHandler]:
    """Create a request handler bound to one generated site directory."""

    class SiteRequestHandler(SimpleHTTPRequestHandler):
        """Serve clean static routes and an optional hosting path prefix."""

        def __init__(
            self,
            request: socket.socket | tuple[bytes, socket.socket],
            client_address: tuple[str, int] | tuple[str, int, int, int],
            server: BaseServer,
        ) -> None:
            """Initialize the handler with the generated site root."""

            super().__init__(
                request,
                client_address,
                server,
                directory=str(site_directory),
            )

        def _prepare_request_path(self) -> bool:
            """Strip the configured public prefix before filesystem resolution."""

            if not base_path:
                return True
            parsed_path = urlsplit(self.path)
            if parsed_path.path == "/":
                self.send_response(HTTPStatus.TEMPORARY_REDIRECT)
                self.send_header("Location", base_path + "/")
                self.end_headers()
                return False
            if not (parsed_path.path == base_path or parsed_path.path.startswith(base_path + "/")):
                self.send_error(HTTPStatus.NOT_FOUND)
                return False
            relative_path = parsed_path.path[len(base_path) :] or "/"
            self.path = urlunsplit(
                (
                    "",
                    "",
                    relative_path,
                    parsed_path.query,
                    "",
                )
            )
            return True

        def do_GET(self) -> None:
            """Serve one GET request after removing the public prefix."""

            if self._prepare_request_path():
                super().do_GET()

        def do_HEAD(self) -> None:
            """Serve one HEAD request after removing the public prefix."""

            if self._prepare_request_path():
                super().do_HEAD()

        def send_error(
            self,
            code: int,
            message: str | None = None,
            explain: str | None = None,
        ) -> None:
            """Use the generated 404 page for local missing-route responses."""

            not_found_path = site_directory / "404.html"
            if code != HTTPStatus.NOT_FOUND or not not_found_path.is_file():
                super().send_error(code, message, explain)
                return
            body = not_found_path.read_bytes()
            self.send_response(HTTPStatus.NOT_FOUND)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def end_headers(self) -> None:
            """Disable caching so rebuilds are visible immediately."""

            self.send_header("Cache-Control", "no-store")
            super().end_headers()

    return SiteRequestHandler


def create_local_server(
    *,
    site_directory: Path,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    base_path: str = "",
) -> ThreadingHTTPServer:
    """Create a threaded local server without starting its request loop."""

    normalized_base_path = normalize_base_path(base_path)
    request_handler = _request_handler_type(
        site_directory=site_directory,
        base_path=normalized_base_path,
    )
    return ThreadingHTTPServer((host, port), request_handler)


def _argument_parser() -> argparse.ArgumentParser:
    """Build the local-server command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST, help="listen address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="listen port")
    parser.add_argument(
        "--base-path",
        type=normalize_base_path,
        default="",
        help="optional URL prefix such as /kisa-cce-guide-web",
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="serve the existing build/site directory without rebuilding",
    )
    return parser


def main() -> int:
    """Build the site and run the local HTTP server until interrupted."""

    arguments = _argument_parser().parse_args()
    repository = repository_root()
    site_directory = repository / "build" / "site"
    if not arguments.no_build:
        build(root=repository, base_path=arguments.base_path)
    elif not (site_directory / "index.html").is_file():
        print("build/site/index.html is missing; run without --no-build", file=sys.stderr)
        return 1
    try:
        server = create_local_server(
            site_directory=site_directory,
            host=arguments.host,
            port=arguments.port,
            base_path=arguments.base_path,
        )
    except OSError as error:
        print(f"failed to start local server: {error}", file=sys.stderr)
        return 1
    actual_port = int(server.server_address[1])
    public_path = arguments.base_path + "/" if arguments.base_path else "/"
    print(f"local site: http://{arguments.host}:{actual_port}{public_path}")
    print("press Ctrl-C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopping local server")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

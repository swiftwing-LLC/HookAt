from __future__ import annotations

import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .api import HookAtAPI, dumps_response
from .config import Config


class HookAtRequestHandler(BaseHTTPRequestHandler):
    api: HookAtAPI
    static_dir: Path

    def do_OPTIONS(self) -> None:
        self._handle_api()

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self._handle_api()
        else:
            self._serve_static()

    def do_POST(self) -> None:
        self._handle_api()

    def do_PATCH(self) -> None:
        self._handle_api()

    def do_DELETE(self) -> None:
        self._handle_api()

    def log_message(self, format: str, *args) -> None:
        return

    def _handle_api(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        response = self.api.handle(
            self.command,
            self.path,
            dict(self.headers.items()),
            body,
            client_ip=self.client_address[0],
        )
        payload = dumps_response(response)
        self.send_response(response.status)
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _serve_static(self) -> None:
        parsed = urlparse(self.path)
        requested = unquote(parsed.path).lstrip("/") or "index.html"
        if requested.endswith("/"):
            requested += "index.html"
        target = (self.static_dir / requested).resolve()
        root = self.static_dir.resolve()
        if root not in target.parents and target != root:
            self.send_error(403)
            return
        if not target.exists() or not target.is_file():
            self.send_error(404)
            return
        content = target.read_bytes()
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    config = Config()
    HookAtRequestHandler.api = HookAtAPI(config)
    HookAtRequestHandler.static_dir = config.static_dir
    server = ThreadingHTTPServer((host, port), HookAtRequestHandler)
    print(f"HookAt backend running on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()

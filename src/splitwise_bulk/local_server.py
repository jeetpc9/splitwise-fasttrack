from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

DEFAULT_PORT = 8765


def _make_handler(on_orders: Callable[[list[dict], str], tuple[int, int]]) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def _json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/api/health", "/health"):
                self._json(200, {"ok": True, "service": "splitwise-fasttrack"})
                return
            self._json(404, {"error": "Not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path not in ("/api/orders", "/orders"):
                self._json(404, {"error": "Not found"})
                return

            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                self._json(400, {"error": "Invalid JSON"})
                return

            orders = data.get("orders", [])
            source = str(data.get("source", "browser"))
            if not isinstance(orders, list):
                self._json(400, {"error": "orders must be a list"})
                return

            try:
                added, skipped = on_orders(orders, source)
            except Exception as exc:
                self._json(500, {"error": str(exc)})
                return

            self._json(200, {"added": added, "skipped": skipped, "total": added + skipped})

    return Handler


class LocalOrderServer:
    """Tiny localhost server so Tampermonkey can push visible orders into the app."""

    def __init__(
        self,
        on_orders: Callable[[list[dict], str], tuple[int, int]],
        *,
        port: int = DEFAULT_PORT,
    ) -> None:
        self.port = port
        self._on_orders = on_orders
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        if self._httpd is not None:
            return
        handler = _make_handler(self._on_orders)
        self._httpd = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        self._httpd = None
        self._thread = None

"""Tiny static server + API proxy for the Omni-Radar web console.

Serves the static UI from this directory and reverse-proxies ``/api/*`` and
``/health`` to the middleware, so the browser talks to a single origin and we
need no CORS changes on the API itself.

Usage:
    python serve.py                      # serves on :8080, proxies to :8000
    python serve.py --port 8080 --api http://localhost:8000

Stdlib only — no dependencies.
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROXY_PREFIXES = ("/api/", "/api", "/health")


class Handler(http.server.SimpleHTTPRequestHandler):
    api_base = "http://localhost:8000"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health" or self.path.startswith("/api"):
            self._proxy()
        else:
            super().do_GET()

    def _proxy(self) -> None:
        url = self.api_base.rstrip("/") + self.path
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                body = resp.read()
                self.send_response(resp.status)
                self.send_header(
                    "Content-Type",
                    resp.headers.get("Content-Type", "application/json"),
                )
                # Forward custom X- headers (e.g. X-Recommended-Poll-Seconds).
                for key, value in resp.headers.items():
                    if key.lower().startswith("x-"):
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as exc:
            body = exc.read()
            self.send_response(exc.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:  # noqa: BLE001
            body = json.dumps(
                {"error": "proxy_failed", "detail": str(exc), "upstream": url}
            ).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        # Quieter logging; keep proxy errors visible.
        if self.path.startswith("/api") or self.path == "/health":
            super().log_message(fmt, *args)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8080)))
    parser.add_argument(
        "--api",
        default=os.environ.get("MIDDLEWARE_URL", "http://localhost:8000"),
        help="Base URL of the middleware API to proxy to.",
    )
    args = parser.parse_args()
    Handler.api_base = args.api

    server = http.server.ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"Omni-Radar console on http://localhost:{args.port}  (proxying -> {args.api})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()

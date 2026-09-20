from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from typesafe_client import JevService, error_payload, load_config


HTML_PATH = Path(__file__).with_name("typesafe_playground.html")


class PlaygroundHandler(BaseHTTPRequestHandler):
    server_version = "JevPlayground/1.0"

    def _send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        self._send_bytes(
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
            status,
        )

    def do_GET(self) -> None:
        if self.path not in ("/", "/index.html"):
            self._send_json({"error": "Not found"}, 404)
            return
        self._send_bytes(HTML_PATH.read_bytes(), "text/html; charset=utf-8")

    def do_POST(self) -> None:
        if self.path != "/api/evaluate":
            self._send_json({"error": "Not found"}, 404)
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length > 64 * 1024:
                raise ValueError("request body is larger than 64 KiB")
            payload = json.loads(self.rfile.read(content_length))
            result = self.server.jev_service.evaluate(payload)
        except Exception as error:  # Keep provider errors visible in the local playground.
            status, response = error_payload(error)
            self._send_json(response, status)
            return

        self._send_json(result)

    def log_message(self, format: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")


class PlaygroundServer(ThreadingHTTPServer):
    def __init__(self, server_address, handler_class, *, profile=None):
        self.jev_service = JevService(load_config(profile=profile))
        super().__init__(server_address, handler_class)

    def server_close(self) -> None:
        self.jev_service.close()
        super().server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Local Jev primitives playground")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--profile", help="Select a profile from [typesafe.profiles]")
    args = parser.parse_args()

    server = PlaygroundServer((args.host, args.port), PlaygroundHandler, profile=args.profile)
    print(f"Jev playground: http://{args.host}:{args.port} (profile={server.jev_service.config.profile})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping playground...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

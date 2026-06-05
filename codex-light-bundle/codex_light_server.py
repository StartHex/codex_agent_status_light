#!/usr/bin/env python3
"""Small HTTP state server for CodexLight.

The server is intended to run next to a remote Codex CLI. Codex hooks report
status with POST /status. A local machine near the BLE light can poll GET
/status and drive the light.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

VALID_MODES = {
    "red",
    "yellow",
    "green",
    "busy",
    "error",
    "thinking",
    "ai",
    "success",
    "traffic",
    "alarm",
    "demo",
    "off",
}

DEFAULT_STATE = {
    "mode": "off",
    "source": "server",
    "event": "startup",
    "tool_name": None,
    "payload": {},
    "seq": 0,
    "updated_at": None,
}


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_state(path: Path) -> dict[str, Any]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(state, dict):
            return {**DEFAULT_STATE, **state}
    except Exception:
        pass
    return dict(DEFAULT_STATE)


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


class CodexLightHandler(BaseHTTPRequestHandler):
    server: "CodexLightHTTPServer"

    def log_message(self, fmt: str, *args: Any) -> None:
        if self.server.quiet:
            return
        super().log_message(fmt, *args)

    def authenticated(self) -> bool:
        token = self.server.api_token
        if not token:
            return True
        auth = self.headers.get("Authorization", "")
        header_token = self.headers.get("X-Codex-Light-Token", "")
        return auth == f"Bearer {token}" or header_token == token

    def send_json(self, status: HTTPStatus, data: dict[str, Any]) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict[str, Any] | None:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid json"})
            return None
        if not isinstance(data, dict):
            self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "json body must be an object"})
            return None
        return data

    def current_state(self) -> dict[str, Any]:
        return load_state(self.server.state_file)

    def write_state(self, data: dict[str, Any], manual: bool = False) -> dict[str, Any] | None:
        mode = str(data.get("mode") or "").strip().lower()
        if mode not in VALID_MODES:
            self.send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": f"invalid mode: {mode}", "valid_modes": sorted(VALID_MODES)},
            )
            return None

        state = self.current_state()
        state.update(
            {
                "mode": mode,
                "source": data.get("source") or ("manual" if manual else "codex-hook"),
                "event": data.get("event"),
                "tool_name": data.get("tool_name"),
                "payload": data.get("payload") if isinstance(data.get("payload"), dict) else {},
                "updated_at": now_iso(),
                "manual": manual,
                "seq": int(state.get("seq") or 0) + 1,
            }
        )
        save_state(self.server.state_file, state)
        return state

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self.send_json(HTTPStatus.OK, {"ok": True, "service": "codex-light", "time": now_iso()})
            return
        if path == "/status":
            if not self.authenticated():
                self.send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
                return
            self.send_json(HTTPStatus.OK, {"ok": True, "status": self.current_state()})
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in {"/status", "/mode"}:
            self.send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            return
        if not self.authenticated():
            self.send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
            return
        data = self.read_json()
        if data is None:
            return
        state = self.write_state(data, manual=(path == "/mode"))
        if state is None:
            return
        self.send_json(HTTPStatus.OK, {"ok": True, "status": state})


class CodexLightHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler_class: type[BaseHTTPRequestHandler], args: argparse.Namespace):
        super().__init__(server_address, handler_class)
        self.state_file = Path(args.state_file).expanduser().resolve()
        self.api_token = args.token or os.environ.get("CODEX_LIGHT_API_TOKEN", "")
        self.quiet = args.quiet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the CodexLight HTTP state server.")
    parser.add_argument("--host", default=os.environ.get("CODEX_LIGHT_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("CODEX_LIGHT_PORT", "8765")))
    parser.add_argument(
        "--state-file",
        default=os.environ.get("CODEX_LIGHT_STATE_FILE", "~/.codex/codex-light-status.json"),
    )
    parser.add_argument("--token", default=os.environ.get("CODEX_LIGHT_API_TOKEN", ""))
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_file = Path(args.state_file).expanduser().resolve()
    if not state_file.exists():
        state = dict(DEFAULT_STATE)
        state["updated_at"] = now_iso()
        save_state(state_file, state)

    server = CodexLightHTTPServer((args.host, args.port), CodexLightHandler, args)
    print(f"CodexLight HTTP server listening on http://{args.host}:{args.port}")
    print(f"State file: {state_file}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping CodexLight HTTP server")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

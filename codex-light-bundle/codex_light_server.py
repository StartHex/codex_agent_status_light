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
    "active_sessions": {},
    "seq": 0,
    "updated_at": None,
}

ACTIVE_MODES = {
    "red",
    "yellow",
    "green",
    "busy",
    "error",
    "thinking",
    "ai",
    "traffic",
    "alarm",
    "demo",
}

TERMINAL_EVENTS = {
    "Stop",
    "message.sent",
    "session.ended",
}

MODE_PRIORITY = {
    "alarm": 100,
    "error": 90,
    "yellow": 80,
    "ai": 70,
    "busy": 60,
    "thinking": 50,
    "traffic": 40,
    "red": 30,
    "green": 20,
    "demo": 10,
}

STALE_FALLBACK_SECONDS = int(os.environ.get("CODEX_LIGHT_STALE_FALLBACK_SECONDS", "120"))


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def parse_iso(ts: Any) -> float:
    if not isinstance(ts, str) or not ts:
        return 0
    try:
        return time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return 0


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


def event_name(data: dict[str, Any], payload: dict[str, Any]) -> str:
    return str(data.get("event") or payload.get("hook_event_name") or "")


def session_key(data: dict[str, Any], payload: dict[str, Any]) -> str:
    source = str(data.get("source") or "unknown")

    session_id = payload.get("session_id")
    if session_id:
        return f"{source}:session:{session_id}"

    cc_session = payload.get("session")
    if cc_session:
        return f"{source}:cc-session:{cc_session}"

    project = payload.get("project")
    user_name = payload.get("user_name")
    if project and user_name:
        return f"{source}:cc-project-user:{project}:{user_name}"
    if project:
        return f"{source}:cc-project:{project}"

    cwd = payload.get("cwd")
    if cwd:
        return f"{source}:cwd:{cwd}"

    return f"{source}:global"


def has_real_session_key(payload: dict[str, Any]) -> bool:
    return bool(payload.get("session_id") or payload.get("session"))


def ranked_session(item: tuple[str, dict[str, Any]]) -> tuple[int, str, str]:
    key, session = item
    mode = str(session.get("mode") or "")
    return (MODE_PRIORITY.get(mode, 0), str(session.get("updated_at") or ""), key)


def is_stale_fallback_session(key: str, session: dict[str, Any], now: float) -> bool:
    if STALE_FALLBACK_SECONDS <= 0:
        return False
    if ":session:" in key or ":cc-session:" in key:
        return False
    if session.get("source") != "cc-connect-hook":
        return False
    updated = parse_iso(session.get("updated_at"))
    return updated > 0 and now - updated > STALE_FALLBACK_SECONDS


def aggregate_state(state: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    active_sessions = state.get("active_sessions")
    if not isinstance(active_sessions, dict):
        active_sessions = {}
    now = time.time()
    active_sessions = {
        key: value
        for key, value in active_sessions.items()
        if (
            isinstance(value, dict)
            and str(value.get("mode") or "") in ACTIVE_MODES
            and not is_stale_fallback_session(key, value, now)
        )
    }
    state["active_sessions"] = active_sessions

    if not active_sessions:
        current_mode = str(state.get("mode") or "")
        current_source = str(state.get("source") or "")
        current_event = str(state.get("event") or "")
        current_payload = state.get("payload") if isinstance(state.get("payload"), dict) else {}
        current_updated = parse_iso(state.get("updated_at"))
        current_is_fallback = (
            current_source == "cc-connect-hook"
            and not has_real_session_key(current_payload)
            and current_mode in ACTIVE_MODES
            and current_event not in TERMINAL_EVENTS
        )
        if (
            current_is_fallback
            and STALE_FALLBACK_SECONDS > 0
            and current_updated > 0
        ):
            if time.time() - current_updated <= STALE_FALLBACK_SECONDS:
                return state
            state.update(
                {
                    "mode": "off",
                    "source": "server",
                    "event": "idle-timeout",
                    "tool_name": None,
                    "payload": {},
                    "manual": False,
                }
            )
            return state
        state.update(fallback)
        return state

    _, best = max(active_sessions.items(), key=ranked_session)
    payload = best.get("payload") if isinstance(best.get("payload"), dict) else {}
    state.update(
        {
            "mode": best.get("mode"),
            "source": best.get("source"),
            "event": best.get("event"),
            "tool_name": best.get("tool_name"),
            "payload": {
                **payload,
                "active_count": len(active_sessions),
            },
            "manual": False,
        }
    )
    return state


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
        state = load_state(self.server.state_file)
        tracked_keys = (
            "mode",
            "source",
            "event",
            "tool_name",
            "payload",
            "manual",
            "active_sessions",
        )
        before = json.dumps({key: state.get(key) for key in tracked_keys}, sort_keys=True)
        fallback = {
            "mode": "off",
            "source": "server",
            "event": "idle",
            "tool_name": None,
            "payload": {},
            "updated_at": now_iso(),
            "manual": False,
        }
        state = aggregate_state(state, fallback)
        after = json.dumps({key: state.get(key) for key in tracked_keys}, sort_keys=True)
        if before != after:
            state["updated_at"] = fallback["updated_at"]
            state["seq"] = int(state.get("seq") or 0) + 1
            save_state(self.server.state_file, state)
        return state

    def write_state(self, data: dict[str, Any], manual: bool = False) -> dict[str, Any] | None:
        mode = str(data.get("mode") or "").strip().lower()
        if mode not in VALID_MODES:
            self.send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": f"invalid mode: {mode}", "valid_modes": sorted(VALID_MODES)},
            )
            return None

        state = self.current_state()
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        event = event_name(data, payload)
        source = data.get("source") or ("manual" if manual else "codex-hook")
        timestamp = now_iso()
        seq = int(state.get("seq") or 0) + 1
        active_sessions = state.get("active_sessions")
        if not isinstance(active_sessions, dict):
            active_sessions = {}

        incoming = {
            "mode": mode,
            "source": source,
            "event": event,
            "tool_name": data.get("tool_name"),
            "payload": payload,
            "updated_at": timestamp,
            "manual": manual,
        }

        key = session_key(data, payload)
        if manual:
            # Manual /mode is an explicit override; "off" also clears stale work.
            if mode == "off":
                active_sessions = {}
            state["active_sessions"] = active_sessions
            state.update(incoming)
            state["updated_at"] = timestamp
            state["seq"] = seq
            save_state(self.server.state_file, state)
            return state

        should_track_session = has_real_session_key(payload)
        if event in TERMINAL_EVENTS or mode in {"off", "success"}:
            active_sessions.pop(key, None)
        elif should_track_session and mode in ACTIVE_MODES:
            active_sessions[key] = incoming

        state["active_sessions"] = active_sessions
        fallback = {
            **incoming,
            "updated_at": timestamp,
        }
        state = aggregate_state(state, fallback)
        state.update(
            {
                "updated_at": timestamp,
                "seq": seq,
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

#!/usr/bin/env python3
"""Codex CLI hook adapter for CodexLight.

Reads Codex hook JSON from stdin, maps lifecycle events to CodexLight modes,
and sends the mode through the existing BLE sender. Set CODEX_LIGHT_DRY_RUN=1
to test without hardware.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib import request
from urllib.error import URLError

SCRIPT_DIR = Path(__file__).resolve().parent
BLE_SCRIPT = SCRIPT_DIR / "codex_light_ble.py"
LOG_PATH = SCRIPT_DIR / "codex-light.log"
STATE_PATH = SCRIPT_DIR / "codex-light-state.json"
LOCK_PATH = SCRIPT_DIR / "codex-light-state.lock"
DEFAULT_HTTP_TIMEOUT = 5.0

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

DEBOUNCE_SECONDS = {
    "thinking": 5.0,
    "busy": 8.0,
    "yellow": 1.0,
    "ai": 2.0,
    "success": 3.0,
    "error": 3.0,
    "alarm": 0.5,
    "green": 3.0,
}


def log(message: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as fp:
        fp.write(f"[{ts}] {message}\n")


def load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def should_send(mode: str, payload: dict[str, Any] | None = None) -> bool:
    payload = payload or {}
    state = load_state()
    now = time.time()
    event = payload.get("hook_event_name")
    last_mode = state.get("last_mode")
    last_ts = float(state.get("last_ts") or 0)
    phase = state.get("turn_phase")

    if event == "UserPromptSubmit":
        state["turn_phase"] = "thinking"
        state.pop("build_started", None)
    elif event == "PreToolUse":
        state["turn_phase"] = "busy"
        state["build_started"] = True
    elif event == "PermissionRequest":
        state["turn_phase"] = "awaiting_user"
    elif event == "Stop":
        state["turn_phase"] = ""

    if mode == "thinking" and phase == "busy":
        save_state(state)
        log("skip thinking blocked by busy phase")
        return False
    if mode == "busy" and phase == "busy" and last_mode == "busy":
        save_state(state)
        log("skip sticky busy")
        return False
    if last_mode == mode and now - last_ts < DEBOUNCE_SECONDS.get(mode, 1.0):
        log(f"skip debounce mode={mode}")
        save_state(state)
        return False
    state["last_mode"] = mode
    state["last_ts"] = now
    save_state(state)
    return True


def tool_failed(payload: dict[str, Any]) -> bool:
    response = payload.get("tool_response")
    if isinstance(response, dict):
        for key in ("exit_code", "status", "returncode"):
            value = response.get(key)
            if isinstance(value, int) and value != 0:
                return True
            if isinstance(value, str) and value.lower() in {"error", "failed", "failure"}:
                return True
        text = json.dumps(response, ensure_ascii=False).lower()
        return any(token in text for token in ("exit code: 1", "process exited with code 1"))
    return False


def stop_failed(payload: dict[str, Any]) -> bool:
    text = str(payload.get("last_assistant_message") or "").lower()
    failure_markers = (
        "blocked",
        "failed",
        "failure",
        "error",
        "exception",
        "could not",
        "cannot",
        "没法",
        "失败",
        "报错",
        "阻塞",
    )
    success_markers = ("done", "completed", "success", "已完成", "完成", "成功")
    if any(marker in text for marker in failure_markers):
        return True
    if any(marker in text for marker in success_markers):
        return False
    return False


def map_event(payload: dict[str, Any]) -> str | None:
    event = payload.get("hook_event_name")
    tool_name = str(payload.get("tool_name") or "")

    if event == "SessionStart":
        return "green"
    if event == "UserPromptSubmit":
        return "thinking"
    if event == "PermissionRequest":
        return "yellow"
    if event == "PreToolUse":
        if tool_name == "apply_patch":
            return "ai"
        return "busy"
    if event == "PostToolUse":
        return "error" if tool_failed(payload) else "busy"
    if event == "PreCompact":
        return "yellow"
    if event == "PostCompact":
        return "thinking"
    if event == "SubagentStart":
        return "ai"
    if event == "SubagentStop":
        return "busy"
    if event == "Stop":
        return "error" if stop_failed(payload) else "success"
    return None


def server_url() -> str:
    return os.environ.get("CODEX_LIGHT_SERVER_URL", "").strip().rstrip("/")


def http_token() -> str:
    return os.environ.get("CODEX_LIGHT_API_TOKEN", "").strip()


def minimal_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "hook_event_name": payload.get("hook_event_name"),
        "tool_name": payload.get("tool_name"),
        "cwd": payload.get("cwd"),
        "session_id": payload.get("session_id"),
    }


def post_status(mode: str, payload: dict[str, Any] | None = None) -> int:
    base_url = server_url()
    if not base_url:
        return 1

    body = {
        "mode": mode,
        "source": os.environ.get("CODEX_LIGHT_SOURCE", "codex-hook"),
        "event": minimal_payload(payload).get("hook_event_name"),
        "tool_name": minimal_payload(payload).get("tool_name"),
        "payload": minimal_payload(payload),
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    token = http_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-Codex-Light-Token"] = token

    url = f"{base_url}/status"
    timeout = float(os.environ.get("CODEX_LIGHT_HTTP_TIMEOUT", DEFAULT_HTTP_TIMEOUT))
    req = request.Request(url, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            response_text = resp.read().decode("utf-8", errors="replace").strip()
    except (OSError, URLError) as exc:
        log(f"http post failed mode={mode} url={url} error={exc}")
        return 1
    if response_text:
        log(f"http post ok mode={mode} response={response_text[:300]}")
    else:
        log(f"http post ok mode={mode}")
    return 0


def send_ble_mode(mode: str) -> int:
    python = os.environ.get("CODEX_LIGHT_PYTHON") or sys.executable
    cmd = [python, str(BLE_SCRIPT), mode]
    if os.environ.get("CODEX_LIGHT_DRY_RUN") == "1":
        cmd.append("--dry-run")

    log(f"send mode={mode} cmd={' '.join(cmd)}")
    try:
        completed = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=20,
            check=False,
        )
    except Exception as exc:
        log(f"send failed mode={mode} error={exc}")
        return 1
    if completed.stdout.strip():
        log(completed.stdout.strip())
    if completed.returncode != 0:
        log(f"send returncode={completed.returncode}")
    return completed.returncode


def send_mode(mode: str, payload: dict[str, Any] | None = None) -> int:
    if mode not in VALID_MODES:
        log(f"invalid mode={mode}")
        return 1
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("w", encoding="utf-8") as lock_fp:
        fcntl.flock(lock_fp, fcntl.LOCK_EX)
        if not should_send(mode, payload):
            fcntl.flock(lock_fp, fcntl.LOCK_UN)
            return 0
        fcntl.flock(lock_fp, fcntl.LOCK_UN)

    if server_url():
        result = post_status(mode, payload)
        if result == 0 or os.environ.get("CODEX_LIGHT_HTTP_FALLBACK_BLE") != "1":
            return result
        log("http failed; falling back to BLE")
    return send_ble_mode(mode)


def read_payload() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log("invalid hook json")
        return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", help="手动发送一个 CodexLight mode")
    parser.add_argument("--event", help="手动模拟 Codex hook_event_name")
    args = parser.parse_args()

    if args.mode:
        return send_mode(args.mode.strip().lower())

    payload = read_payload()
    if args.event:
        payload["hook_event_name"] = args.event

    mode = map_event(payload)
    if mode:
        send_mode(mode, payload)
        log(f"event={payload.get('hook_event_name')} tool={payload.get('tool_name')} mode={mode}")
    else:
        log(f"event={payload.get('hook_event_name')} ignored")

    if payload.get("hook_event_name") in {"Stop", "SubagentStop"}:
        print(json.dumps({"continue": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

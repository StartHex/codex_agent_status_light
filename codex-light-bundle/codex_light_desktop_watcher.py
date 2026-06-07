#!/usr/bin/env python3
"""Infer Codex Desktop activity from its local log database.

Codex Desktop does not currently expose the same hook stream as Codex CLI.
This watcher tails ~/.codex/logs_2.sqlite, maps stable log patterns to
CodexLight modes, and reports them to the local HTTP relay.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any
from urllib import request
from urllib.error import URLError

VALID_MODES = {
    "thinking",
    "busy",
    "ai",
    "success",
    "error",
    "yellow",
    "off",
}

THREAD_RE = re.compile(r"thread_id=([0-9a-fA-F-]{36})|thread\.id=([0-9a-fA-F-]{36})")
TURN_RE = re.compile(r"turn_id[=:]\"?([0-9a-fA-F-]{36})|turn\.id=([0-9a-fA-F-]{36})")
FUNCTION_NAME_RE = re.compile(r'"name"\s*:\s*"([^"]+)"')


def now() -> float:
    return time.time()


def log(args: argparse.Namespace, message: str) -> None:
    if args.quiet:
        return
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def load_state(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def first_match(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    if not match:
        return ""
    for group in match.groups():
        if group:
            return group
    return ""


def classify(row: sqlite3.Row) -> dict[str, Any] | None:
    level = str(row["level"] or "")
    target = str(row["target"] or "")
    body = str(row["feedback_log_body"] or "")
    haystack = f"{target} {body}"

    thread_id = first_match(THREAD_RE, haystack)
    turn_id = first_match(TURN_RE, haystack)
    tool_name = first_match(FUNCTION_NAME_RE, body)
    mode = ""
    event = ""

    if level == "ERROR":
        mode = "error"
        event = "desktop.error"
    elif "ToolCall:" in body:
        event = "desktop.tool_call"
        mode = "ai" if "apply_patch" in body else "busy"
        tool_name = tool_name or body.split("ToolCall:", 1)[1].strip().split(" ", 1)[0]
    elif "app-server event: item/commandExecution" in body:
        mode = "busy"
        event = "desktop.command_execution"
    elif '"type":"response.output_item.added"' in body and '"type":"function_call"' in body:
        mode = "busy"
        event = "desktop.function_call.started"
    elif '"type":"response.created"' in body or '"type":"response.in_progress"' in body:
        mode = "thinking"
        event = "desktop.response.started"
    elif '"type":"response.completed"' in body or "event.kind=response.completed" in body:
        mode = "error" if '"status":"failed"' in body or '"error":null' not in body and '"error":' in body else "success"
        event = "desktop.response.completed"
    elif '"type":"response.failed"' in body or '"type":"response.incomplete"' in body:
        mode = "error"
        event = "desktop.response.failed"

    if not mode:
        return None

    return {
        "mode": mode,
        "event": event,
        "tool_name": tool_name or None,
        "payload": {
            "session_id": thread_id or None,
            "thread_id": thread_id,
            "turn_id": turn_id or None,
            "log_id": int(row["id"]),
            "target": target,
        },
    }


def post_status(args: argparse.Namespace, status: dict[str, Any]) -> bool:
    body = {
        "mode": status["mode"],
        "source": "codex-desktop-watcher",
        "event": status["event"],
        "tool_name": status.get("tool_name"),
        "payload": status["payload"],
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
        headers["X-Codex-Light-Token"] = args.token
    req = request.Request(f"{args.server_url.rstrip('/')}/status", data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=args.http_timeout) as resp:
            resp.read()
        return True
    except (OSError, URLError) as exc:
        log(args, f"post failed mode={status['mode']} event={status['event']}: {exc}")
        return False


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=2)
    conn.row_factory = sqlite3.Row
    return conn


def latest_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS id FROM logs").fetchone()
    return int(row["id"] or 0)


def read_rows(conn: sqlite3.Connection, after_id: int, limit: int) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT id, ts, level, target, feedback_log_body
            FROM logs
            WHERE id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (after_id, limit),
        )
    )


def should_send(state: dict[str, Any], status: dict[str, Any], debounce: float) -> bool:
    key = f"{status['mode']}:{status['event']}:{status['payload'].get('session_id')}:{status.get('tool_name') or ''}"
    sent = state.setdefault("sent", {})
    last = float(sent.get(key) or 0)
    if now() - last < debounce:
        return False
    sent[key] = now()
    return True


def remember_thread(state: dict[str, Any], status: dict[str, Any]) -> None:
    payload = status.get("payload") if isinstance(status.get("payload"), dict) else {}
    session_id = payload.get("session_id")
    if isinstance(session_id, str) and session_id:
        state["last_session_id"] = session_id


def fill_missing_thread(state: dict[str, Any], status: dict[str, Any]) -> None:
    payload = status.get("payload") if isinstance(status.get("payload"), dict) else {}
    if payload.get("session_id"):
        return
    last_session_id = state.get("last_session_id")
    if isinstance(last_session_id, str) and last_session_id:
        payload["session_id"] = last_session_id
        payload["thread_id"] = payload.get("thread_id") or last_session_id


def run_once(args: argparse.Namespace, state: dict[str, Any]) -> int:
    db_path = Path(args.db).expanduser()
    conn = connect_readonly(db_path)
    try:
        last_id = int(state.get("last_id") or 0)
        if last_id <= 0:
            last_id = latest_id(conn)
            state["last_id"] = last_id
            return 0
        rows = read_rows(conn, last_id, args.batch_size)
        for row in rows:
            state["last_id"] = int(row["id"])
            status = classify(row)
            if not status or status["mode"] not in VALID_MODES:
                continue
            fill_missing_thread(state, status)
            if should_send(state, status, args.debounce_seconds):
                if post_status(args, status):
                    remember_thread(state, status)
                    log(args, f"mode={status['mode']} event={status['event']} log_id={row['id']}")
        return len(rows)
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watch Codex Desktop logs and report CodexLight status.")
    parser.add_argument("--db", default=os.environ.get("CODEX_DESKTOP_LOG_DB", "~/.codex/logs_2.sqlite"))
    parser.add_argument("--state-file", default=os.environ.get("CODEX_DESKTOP_LIGHT_STATE", "~/.codex/codex-light-desktop-watcher.json"))
    parser.add_argument("--server-url", default=os.environ.get("CODEX_LIGHT_SERVER_URL", "http://127.0.0.1:8765"))
    parser.add_argument("--token", default=os.environ.get("CODEX_LIGHT_API_TOKEN", ""))
    parser.add_argument("--interval", type=float, default=float(os.environ.get("CODEX_DESKTOP_LIGHT_INTERVAL", "0.5")))
    parser.add_argument("--error-interval", type=float, default=3.0)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--debounce-seconds", type=float, default=0.5)
    parser.add_argument("--http-timeout", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_path = Path(args.state_file).expanduser()
    state = load_state(state_path)
    while True:
        try:
            run_once(args, state)
            save_state(state_path, state)
            if args.once:
                return 0
            time.sleep(args.interval)
        except KeyboardInterrupt:
            save_state(state_path, state)
            return 0
        except Exception as exc:
            log(args, f"watch error: {exc}")
            save_state(state_path, state)
            if args.once:
                return 1
            time.sleep(args.error_interval)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""HTTP client and local light poller for CodexLight."""

from __future__ import annotations

import argparse
import glob
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


def headers(token: str = "") -> dict[str, str]:
    result = {"Accept": "application/json"}
    if token:
        result["Authorization"] = f"Bearer {token}"
        result["X-Codex-Light-Token"] = token
    return result


def request_json(base_url: str, path: str, token: str = "", data: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    body = None
    req_headers = headers(token)
    method = "GET"
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
        method = "POST"
    req = request.Request(url, data=body, headers=req_headers, method=method)
    with request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def send_ble(mode: str, dry_run: bool = False) -> int:
    python = os.environ.get("CODEX_LIGHT_PYTHON") or sys.executable
    cmd = [python, str(BLE_SCRIPT), mode]
    if dry_run:
        cmd.append("--dry-run")
    completed = subprocess.run(cmd, check=False)
    return completed.returncode


def find_serial_port() -> str:
    for pattern in (
        os.environ.get("CODEX_LIGHT_SERIAL_PORT", ""),
        "/dev/cu.usbmodem*",
        "/dev/ttyACM*",
        "/dev/ttyUSB*",
    ):
        if not pattern:
            continue
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[0]
    return ""


def send_serial(mode: str, port: str = "", dry_run: bool = False) -> int:
    port = port or find_serial_port()
    if not port:
        print("serial send failed: no serial port found", file=sys.stderr)
        return 5
    if dry_run:
        print(f"[dry-run] CodexLight serial port={port} mode={mode}")
        return 0
    try:
        import serial
    except ImportError:
        print("serial send failed: missing pyserial; install with python3 -m pip install pyserial", file=sys.stderr)
        return 4
    try:
        with serial.Serial(port, 115200, timeout=2, write_timeout=2) as connection:
            connection.dtr = False
            connection.rts = False
            time.sleep(0.05)
            connection.write((mode + "\n").encode("utf-8"))
            connection.flush()
        return 0
    except OSError as exc:
        print(f"serial send failed port={port}: {exc}", file=sys.stderr)
        return 6


def send_light(mode: str, driver: str = "auto", serial_port: str = "", dry_run: bool = False) -> int:
    if driver == "serial":
        return send_serial(mode, port=serial_port, dry_run=dry_run)
    if driver == "ble":
        return send_ble(mode, dry_run=dry_run)
    port = serial_port or find_serial_port()
    if port:
        return send_serial(mode, port=port, dry_run=dry_run)
    return send_ble(mode, dry_run=dry_run)


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def run_status(args: argparse.Namespace) -> int:
    print_json(request_json(args.server_url, "/status", args.token))
    return 0


def run_send(args: argparse.Namespace) -> int:
    mode = args.mode.strip().lower()
    if mode not in VALID_MODES:
        raise SystemExit(f"invalid mode: {mode}")
    print_json(
        request_json(
            args.server_url,
            "/mode",
            args.token,
            {"mode": mode, "source": args.source, "event": "manual"},
        )
    )
    return 0


def extract_status(response: dict[str, Any]) -> dict[str, Any]:
    status = response.get("status")
    if not isinstance(status, dict):
        raise RuntimeError(f"unexpected server response: {response}")
    return status


def run_poll(args: argparse.Namespace) -> int:
    last_seq: int | None = None
    last_mode = ""
    while True:
        try:
            response = request_json(args.server_url, "/status", args.token)
            status = extract_status(response)
            mode = str(status.get("mode") or "").strip().lower()
            seq = int(status.get("seq") or 0)
            should_send = args.force or mode != last_mode or (args.send_on_seq and seq != last_seq)
            if mode in VALID_MODES and should_send:
                print(f"CodexLight seq={seq} mode={mode} source={status.get('source')}")
                rc = send_light(mode, driver=args.driver, serial_port=args.serial_port, dry_run=args.dry_run)
                if rc == 0:
                    last_seq = seq
                    last_mode = mode
                else:
                    print(f"light send failed with exit code {rc}", file=sys.stderr)
            time.sleep(args.interval)
        except KeyboardInterrupt:
            return 0
        except (OSError, URLError, RuntimeError, ValueError) as exc:
            print(f"poll error: {exc}", file=sys.stderr)
            time.sleep(args.error_interval)


def parse_args() -> argparse.Namespace:
    default_url = os.environ.get("CODEX_LIGHT_SERVER_URL", "http://127.0.0.1:8765")
    default_token = os.environ.get("CODEX_LIGHT_API_TOKEN", "")
    parser = argparse.ArgumentParser(description="Query, set, or poll CodexLight HTTP status.")
    parser.add_argument("--server-url", default=default_url)
    parser.add_argument("--token", default=default_token)
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="Read current server status")
    status.set_defaults(func=run_status)

    send = subparsers.add_parser("send", help="Set a manual light mode on the server")
    send.add_argument("mode", choices=sorted(VALID_MODES))
    send.add_argument("--source", default="manual-client")
    send.set_defaults(func=run_send)

    poll = subparsers.add_parser("poll", help="Poll server status and send mode to BLE")
    poll.add_argument("--interval", type=float, default=1.0)
    poll.add_argument("--error-interval", type=float, default=5.0)
    poll.add_argument("--driver", choices=("auto", "serial", "ble"), default=os.environ.get("CODEX_LIGHT_DRIVER", "auto"))
    poll.add_argument("--serial-port", default=os.environ.get("CODEX_LIGHT_SERIAL_PORT", ""))
    poll.add_argument("--dry-run", action="store_true")
    poll.add_argument("--force", action="store_true", help="Send every poll even when seq/mode did not change")
    poll.add_argument(
        "--send-on-seq",
        action="store_true",
        help="Send when the server sequence changes even if the aggregate mode did not change",
    )
    poll.set_defaults(func=run_poll)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

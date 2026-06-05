# CodexLight

CodexLight lets the ESP32-C3 status light show Codex CLI status.
It uses Codex lifecycle hooks and the existing BLE sender.
It can also run through an HTTP relay when Codex CLI is on a remote server.

## Status mapping

| Codex event | Light mode |
|---|---|
| `SessionStart` | `green` |
| `UserPromptSubmit` | `thinking` |
| `PreToolUse` | `busy`, or `ai` for `apply_patch` |
| `PermissionRequest` | `yellow` |
| `PostToolUse` failure | `error` |
| `Stop` | `success`, or `error` when the final assistant text looks failed/blocked |

## Install

```bash
cd codex-light-bundle
./install-codex-light.sh
```

Codex hooks are enabled by default in recent Codex CLI versions. After install,
start `codex` and run `/hooks` to review and trust the new hook definitions.

## Test without hardware

```bash
CODEX_LIGHT_DRY_RUN=1 python3 ~/.codex/hooks/codex-light/codex_light.py --mode thinking
CODEX_LIGHT_DRY_RUN=1 python3 ~/.codex/hooks/codex-light/codex_light.py --event UserPromptSubmit <<'JSON'
{"hook_event_name":"UserPromptSubmit","prompt":"test","cwd":"/tmp"}
JSON
```

The dry-run mode writes logs to:

```text
~/.codex/hooks/codex-light/codex-light.log
```

## Real hardware

Install `bleak` and unset `CODEX_LIGHT_DRY_RUN`:

```bash
python3 -m pip install bleak
python3 ~/.codex/hooks/codex-light/codex_light_ble.py green
```

## HTTP relay

On the Codex server:

```bash
python3 ~/.codex/hooks/codex-light/codex_light_server.py --host 0.0.0.0 --port 8765
export CODEX_LIGHT_SERVER_URL='http://SERVER_IP:8765'
```

On the local machine near the BLE light:

```bash
python3 -m pip install bleak
export CODEX_LIGHT_SERVER_URL='http://SERVER_IP:8765'
python3 ~/.codex/hooks/codex-light/codex_light_http_client.py poll
```

Use `CODEX_LIGHT_API_TOKEN` on both sides if the relay is reachable by other
machines.

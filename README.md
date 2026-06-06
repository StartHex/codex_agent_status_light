# CodexLight

CodexLight is an ESP32-C3 BLE desktop status light for Codex CLI. It maps Codex
agent lifecycle events to red/yellow/green traffic-light effects.

## Status Mapping

| Codex event | Mode | Meaning |
|---|---|---|
| `SessionStart` | `green` | Session started or resumed |
| `UserPromptSubmit` | `thinking` | New user task submitted |
| `PreToolUse` | `busy` | Tool or command is running |
| `PreToolUse` with `apply_patch` | `ai` | Code edit is being applied |
| `PermissionRequest` | `yellow` | Waiting for user approval |
| Failed `PostToolUse` | `error` | Tool failed |
| `Stop` | `success` / `error` | Turn finished |

## Files

```text
ESP32_C3_ToyBoard_CommonAnode_BLE_Enhanced_CodexLight.ino
codex-light-bundle/
├─ codex_light.py
├─ codex_light_ble.py
├─ codex_light_http_client.py
├─ codex_light_server.py
├─ codex-hooks.json.snippet
└─ install-codex-light.sh
```

## Hardware

This build targets an ESP32-C3 SuperMini and a common-anode three-light board.

| Light | ESP32 pin |
|---|---|
| Green | IO2 |
| Yellow | IO3 |
| Red | IO4 |

Wiring:

```text
ESP32 3.3V -> board +
ESP32 IO2  -> 220 ohm -> green control point
ESP32 IO3  -> 220 ohm -> yellow control point
ESP32 IO4  -> 220 ohm -> red control point
```

Common-anode logic:

```text
GPIO LOW  = on
GPIO HIGH = off
```

## Firmware

Flash:

```text
ESP32_C3_ToyBoard_CommonAnode_BLE_Enhanced_CodexLight.ino
```

BLE parameters:

```text
Device Name: CodexLight
Service UUID: b8b7e001-7a6b-4f4f-9a8b-11c0ffee0001
Mode Characteristic UUID: b8b7e002-7a6b-4f4f-9a8b-11c0ffee0001
```

Supported modes:

```text
demo / thinking / ai / busy / success / error / alarm / traffic / off / red / yellow / green
```

## Install Codex Hooks

```bash
cd codex-light-bundle
./install-codex-light.sh
```

Then start Codex CLI and run:

```text
/hooks
```

Review and trust the new hook definitions.

If hooks are disabled, enable them in `~/.codex/config.toml`:

```toml
[features]
hooks = true
```

## Test Without Hardware

```bash
CODEX_LIGHT_DRY_RUN=1 python3 codex-light-bundle/codex_light.py --mode thinking
CODEX_LIGHT_DRY_RUN=1 python3 codex-light-bundle/codex_light_ble.py success
CODEX_LIGHT_DRY_RUN=1 python3 codex-light-bundle/codex_light.py --event UserPromptSubmit <<'JSON'
{"hook_event_name":"UserPromptSubmit","prompt":"test","cwd":"/tmp"}
JSON
```

Logs:

```bash
tail -f codex-light-bundle/codex-light.log
```

## Use Real Hardware

Install BLE dependency:

```bash
python3 -m pip install bleak
```

Send a manual mode:

```bash
python3 codex-light-bundle/codex_light_ble.py green
```

If the board still advertises another BLE name, either reflash the firmware or
override the device name:

```bash
CODEX_LIGHT_DEVICE_NAME=CodexLight python3 codex-light-bundle/codex_light_ble.py green
```

## HTTP Relay Mode

Use this mode when Codex CLI runs on a remote server, but the ESP32 light is
near your local Mac/Windows/Linux machine. The local poller can drive the light
through BLE or through the ESP32-C3 USB serial port.

Architecture:

```text
Remote Codex CLI hooks
  -> POST http://server:8765/status
  -> local poller GET http://server:8765/status
  -> local BLE or USB serial write to CodexLight
```

Run the HTTP status server on the Codex server:

```bash
python3 codex-light-bundle/codex_light_server.py --host 0.0.0.0 --port 8765
```

Optional token protection:

```bash
export CODEX_LIGHT_API_TOKEN='change-me'
python3 codex-light-bundle/codex_light_server.py --host 0.0.0.0 --port 8765
```

Configure the Codex hook environment on the Codex server:

```bash
export CODEX_LIGHT_SERVER_URL='http://SERVER_IP:8765'
export CODEX_LIGHT_API_TOKEN='change-me'
```

Then install hooks as usual:

```bash
cd codex-light-bundle
./install-codex-light.sh
```

On the local machine near the light, start the poller. For BLE, install
`bleak`. For USB serial, install `pyserial` and set `CODEX_LIGHT_DRIVER=serial`.

```bash
export CODEX_LIGHT_SERVER_URL='http://SERVER_IP:8765'
export CODEX_LIGHT_API_TOKEN='change-me'
python3 codex-light-bundle/codex_light_http_client.py poll
```

USB serial mode:

```bash
python3 -m pip install pyserial
export CODEX_LIGHT_DRIVER=serial
export CODEX_LIGHT_SERIAL_PORT=/dev/cu.usbmodem1101
python3 codex-light-bundle/codex_light_http_client.py poll
```

To run the Mac poller as a LaunchAgent, copy and edit the template:

```bash
mkdir -p ~/Library/LaunchAgents ~/Library/Logs/CodexLight
cp codex-light-bundle/com.codexlight.poller.plist.example \
  ~/Library/LaunchAgents/com.codexlight.poller.plist
plutil -lint ~/Library/LaunchAgents/com.codexlight.poller.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.codexlight.poller.plist
launchctl kickstart -k gui/$(id -u)/com.codexlight.poller
```

Replace `YOUR_USER`, `SERVER_IP`, and `change-me` before loading the agent.

Manual status query and light control:

```bash
python3 codex-light-bundle/codex_light_http_client.py status
python3 codex-light-bundle/codex_light_http_client.py send green
python3 codex-light-bundle/codex_light_http_client.py send off
```

No-hardware relay test:

```bash
python3 codex-light-bundle/codex_light_server.py --host 127.0.0.1 --port 8765
CODEX_LIGHT_SERVER_URL=http://127.0.0.1:8765 python3 codex-light-bundle/codex_light.py --mode thinking
python3 codex-light-bundle/codex_light_http_client.py poll --dry-run
```

## cc-connect Hooks

When Codex is launched by `cc-connect` as `codex exec --json`, Codex CLI hooks
may not be the best status source. Use `cc-connect` lifecycle hooks to report
coarse status into the same HTTP relay:

```toml
[[hooks]]
event = "message.received"
type = "command"
command = "/home/ubuntu/.codex/hooks/codex-light/cc_connect_light.sh thinking message.received"
async = true
timeout = 5

[[hooks]]
event = "message.sent"
type = "command"
command = "/home/ubuntu/.codex/hooks/codex-light/cc_connect_light.sh off message.sent"
async = true
timeout = 5
```

Typical mapping:

| cc-connect event | Mode |
|---|---|
| `message.received` | `thinking` |
| `session.started` | `green` |
| `permission.requested` | `yellow` |
| `error` | `error` |
| `message.sent` | `off` |

The HTTP relay tracks active sessions before exposing a single light mode. If
two Codex tasks are running and one finishes first, its terminal event only
removes that session; the light stays on for the remaining active task. Events
without a real session id are treated as transient status and time out instead
of being tracked as active work. The bundled `cc_connect_light.sh` reads
`CC_HOOK_SESSION_KEY`, which is the cc-connect session identifier used to pair
`message.received` with the matching `message.sent`.

## Environment Variables

| Variable | Purpose |
|---|---|
| `CODEX_LIGHT_DRY_RUN=1` | Do not scan BLE; only log/print mode |
| `CODEX_LIGHT_PYTHON=/path/to/python3` | Python executable used by hook adapter |
| `CODEX_LIGHT_DEVICE_NAME=CodexLight` | BLE advertised device name |
| `CODEX_LIGHT_SERVER_URL=http://server:8765` | Send hook status to the HTTP relay instead of direct BLE |
| `CODEX_LIGHT_API_TOKEN=...` | Optional shared token for HTTP relay requests |
| `CODEX_LIGHT_DRIVER=auto|serial|ble` | Local HTTP poller driver selection |
| `CODEX_LIGHT_SERIAL_PORT=/dev/cu.usbmodem1101` | Serial port used by the local poller |
| `CODEX_LIGHT_HTTP_TIMEOUT=5` | HTTP reporting timeout in seconds |
| `CODEX_LIGHT_HTTP_FALLBACK_BLE=1` | Fall back to local BLE if HTTP reporting fails |
| `CODEX_LIGHT_HOST=0.0.0.0` | Default HTTP server listen host |
| `CODEX_LIGHT_PORT=8765` | Default HTTP server listen port |
| `CODEX_LIGHT_STATE_FILE=/path/status.json` | HTTP server state file |
| `CODEX_LIGHT_DEST=/path` | Installer destination override |
| `CODEX_HOOKS_FILE=/path/hooks.json` | Installer hooks file override |

## Uninstall

```bash
rm -rf ~/.codex/hooks/codex-light
nano ~/.codex/hooks.json
```

Remove the `codex-light` hook entries, then restart Codex CLI.

## References

- Codex hooks: `https://developers.openai.com/codex/hooks`
- Arduino IDE: `https://www.arduino.cc/en/software`
- Arduino ESP32 docs: `https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html`

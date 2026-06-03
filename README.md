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

## Environment Variables

| Variable | Purpose |
|---|---|
| `CODEX_LIGHT_DRY_RUN=1` | Do not scan BLE; only log/print mode |
| `CODEX_LIGHT_PYTHON=/path/to/python3` | Python executable used by hook adapter |
| `CODEX_LIGHT_DEVICE_NAME=CodexLight` | BLE advertised device name |
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

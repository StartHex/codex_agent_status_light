#!/bin/bash
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_DIR="${CODEX_LIGHT_DEST:-$HOME/.codex/hooks/codex-light}"
HOOKS_FILE="${CODEX_HOOKS_FILE:-$HOME/.codex/hooks.json}"

if ! mkdir -p "$DEST_DIR"; then
  echo "Cannot create $DEST_DIR."
  echo "Run this installer from your normal terminal, or set CODEX_LIGHT_DEST to a writable path."
  exit 1
fi
cp "$SRC_DIR/codex_light.py" "$DEST_DIR/"
cp "$SRC_DIR/codex_light_ble.py" "$DEST_DIR/"
cp "$SRC_DIR/codex_light_http_client.py" "$DEST_DIR/"
cp "$SRC_DIR/codex_light_server.py" "$DEST_DIR/"
chmod +x "$DEST_DIR/codex_light.py"
chmod +x "$DEST_DIR/codex_light_http_client.py"
chmod +x "$DEST_DIR/codex_light_server.py"

if ! mkdir -p "$(dirname "$HOOKS_FILE")"; then
  echo "Cannot create $(dirname "$HOOKS_FILE")."
  echo "Run this installer from your normal terminal, or set CODEX_HOOKS_FILE to a writable path."
  exit 1
fi
if [[ -e "$HOOKS_FILE" ]]; then
  BACKUP="${HOOKS_FILE}.bak.$(date +%Y%m%d%H%M%S)"
  cp "$HOOKS_FILE" "$BACKUP"
  echo "Existing hooks file backed up to: $BACKUP"
  echo "Please merge this snippet manually if you already have hooks:"
  echo "$SRC_DIR/codex-hooks.json.snippet"
else
  cp "$SRC_DIR/codex-hooks.json.snippet" "$HOOKS_FILE"
  echo "Installed Codex hooks to: $HOOKS_FILE"
fi

echo "Installed CodexLight scripts to: $DEST_DIR"
echo "No-hardware test:"
echo "  CODEX_LIGHT_DRY_RUN=1 python3 \"$DEST_DIR/codex_light.py\" --mode thinking"
echo "Then start codex and run /hooks to review and trust the new hooks."

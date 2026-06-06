#!/usr/bin/env bash
set -euo pipefail

mode="${1:-}"
event="${2:-cc-connect}"

case "$mode" in
  red|yellow|green|busy|error|thinking|ai|success|traffic|alarm|demo|off) ;;
  *) echo "invalid mode: $mode" >&2; exit 2 ;;
esac

set -a
. /etc/codex-light-http.env
set +a

payload="$(python3 - "$mode" "$event" <<'PY'
import json
import os
import sys

mode, event = sys.argv[1], sys.argv[2]
print(json.dumps({
    "mode": mode,
    "source": "cc-connect-hook",
    "event": event,
    "payload": {
        "project": os.environ.get("CC_HOOK_PROJECT") or os.environ.get("CC_PROJECT", ""),
        "session": os.environ.get("CC_HOOK_SESSION") or os.environ.get("CC_SESSION_KEY", ""),
        "message_id": os.environ.get("CC_HOOK_MESSAGE_ID", ""),
        "user_name": os.environ.get("CC_HOOK_USER_NAME", ""),
    },
}, ensure_ascii=False))
PY
)"

curl -fsS \
  -X POST \
  -H "Authorization: Bearer ${CODEX_LIGHT_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$payload" \
  "${CODEX_LIGHT_SERVER_URL%/}/status" >/dev/null

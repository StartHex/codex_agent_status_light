from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = REPO_ROOT / "codex-light-bundle" / "codex_light_server.py"


def load_server_module():
    spec = importlib.util.spec_from_file_location("codex_light_server", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {SERVER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ServerAggregationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_server_module()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_file = Path(self.tmpdir.name) / "state.json"
        state = dict(self.module.DEFAULT_STATE)
        state["updated_at"] = self.module.now_iso()
        self.module.save_state(self.state_file, state)
        args = argparse.Namespace(state_file=str(self.state_file), token="", quiet=True)
        self.server = self.module.CodexLightHTTPServer(
            ("127.0.0.1", 0),
            self.module.CodexLightHandler,
            args,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tmpdir.cleanup()

    def post_status(self, body: dict) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}/status",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))["status"]

    def test_one_finished_session_does_not_clear_other_active_session(self) -> None:
        first = {"session_id": "session-a"}
        second = {"session_id": "session-b"}

        state = self.post_status(
            {
                "mode": "thinking",
                "source": "codex-cli",
                "event": "started",
                "payload": first,
            }
        )
        self.assertEqual(state["mode"], "thinking")
        self.assertEqual(state["payload"]["active_count"], 1)

        state = self.post_status(
            {
                "mode": "thinking",
                "source": "codex-cli",
                "event": "started",
                "payload": second,
            }
        )
        self.assertEqual(state["mode"], "thinking")
        self.assertEqual(state["payload"]["active_count"], 2)

        state = self.post_status(
            {
                "mode": "off",
                "source": "codex-cli",
                "event": "session.ended",
                "payload": first,
            }
        )
        self.assertEqual(state["mode"], "thinking")
        self.assertEqual(state["payload"]["active_count"], 1)
        self.assertIn("codex-cli:session:session-b", state["active_sessions"])

        state = self.post_status(
            {
                "mode": "off",
                "source": "codex-cli",
                "event": "session.ended",
                "payload": second,
            }
        )
        self.assertEqual(state["mode"], "off")
        self.assertEqual(state["event"], "idle")
        self.assertEqual(state["active_sessions"], {})


if __name__ == "__main__":
    unittest.main()

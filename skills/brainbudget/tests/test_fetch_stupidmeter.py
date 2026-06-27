from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import sys

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import fetch_stupidmeter  # noqa: E402


class FetchStupidMeterTests(unittest.TestCase):
    def test_fetch_writes_dashboard_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            def fake_fetch(url: str, timeout: int):
                if "period=7d" in url:
                    return {"models": [{"model": "gpt-5.1-codex", "score": 68}]}, 200
                return {"models": [{"model": "gpt-5.1-codex", "score": 66}]}, 200

            with mock.patch.object(fetch_stupidmeter, "fetch_json", side_effect=fake_fetch):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    exit_code = fetch_stupidmeter.main(["--root", str(root), "--cache", ".arc/stupidmeter_cache.json"])
            self.assertEqual(exit_code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertTrue(payload["requests"]["dashboard"]["ok"])
            self.assertTrue(payload["requests"]["history"]["ok"])
            cache = json.loads((root / ".arc" / "stupidmeter_cache.json").read_text(encoding="utf-8"))
            self.assertEqual(cache["requests"]["dashboard"]["data"]["models"][0]["score"], 66)

    def test_fetch_uses_cache_after_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cache_path = root / ".arc" / "stupidmeter_cache.json"
            cache_path.parent.mkdir(parents=True)
            cache_path.write_text(
                json.dumps({"ok": True, "fetched_at_epoch": 1, "requests": {"dashboard": {"ok": True}}}),
                encoding="utf-8",
            )
            with mock.patch.object(fetch_stupidmeter, "fetch_json", side_effect=OSError("network down")):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    exit_code = fetch_stupidmeter.main(
                        ["--root", str(root), "--cache", ".arc/stupidmeter_cache.json"]
                    )
            self.assertEqual(exit_code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertFalse(payload["ok"])
            self.assertTrue(payload["cache_used"])


if __name__ == "__main__":
    unittest.main()

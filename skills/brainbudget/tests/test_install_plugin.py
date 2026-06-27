from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[3]
INSTALLER = PLUGIN_ROOT / "scripts" / "install-plugin"


class InstallPluginTests(unittest.TestCase):
    def test_installer_creates_marketplace_and_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as home_dir:
            home = Path(home_dir)
            codex_home = home / ".codex"
            completed = subprocess.run(
                ["python3", str(INSTALLER), "--install-profiles"],
                cwd=PLUGIN_ROOT,
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "HOME": str(home), "CODEX_HOME": str(codex_home)},
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            json_start = completed.stdout.rfind("{")
            self.assertNotEqual(json_start, -1, completed.stdout)
            payload = json.loads(completed.stdout[json_start:])
            self.assertEqual(payload["plugin_name"], "brainbudget")
            self.assertEqual(payload["marketplace_name"], "personal")
            plugin_link = Path(payload["plugin_link"])
            self.assertTrue(plugin_link.is_symlink())
            self.assertEqual(plugin_link.resolve(), PLUGIN_ROOT.resolve())

            marketplace = json.loads((home / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
            entries = {entry["name"]: entry for entry in marketplace["plugins"]}
            self.assertIn("brainbudget", entries)
            self.assertEqual(entries["brainbudget"]["source"]["path"], "./plugins/brainbudget")

            self.assertTrue((codex_home / "arc-p0.config.toml").exists())
            self.assertTrue((codex_home / "arc-p3.config.toml").exists())


if __name__ == "__main__":
    unittest.main()

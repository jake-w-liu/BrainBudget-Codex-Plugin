from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[3]
WRAPPER = PLUGIN_ROOT / "scripts" / "arc-codex"
HOOK = PLUGIN_ROOT / "hooks" / "user_prompt_submit_arc.py"
PLUGIN_HOOKS_JSON = PLUGIN_ROOT / "hooks" / "hooks.json"


class WrapperAndHookTests(unittest.TestCase):
    def make_project(self) -> Path:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        (root / "tests").mkdir()
        (root / "pyproject.toml").write_text("[project]\nname='tmp'\nversion='0.0.0'\n", encoding="utf-8")
        return root

    def make_codex_stub(self, root: Path) -> tuple[Path, Path]:
        stub = root / "fake-codex"
        capture = root / "codex-argv.json"
        stub.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env python3",
                    "import json",
                    "import sys",
                    f"capture = {json.dumps(str(capture))}",
                    "with open(capture, 'w', encoding='utf-8') as handle:",
                    "    json.dump(sys.argv[1:], handle)",
                    "print('{\"type\":\"turn.completed\"}')",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        stub.chmod(0o755)
        return stub, capture

    def test_wrapper_dry_run_writes_policy(self) -> None:
        root = self.make_project()
        completed = subprocess.run(
            [str(WRAPPER), "--dry-run", "--skip-fetch", "summarize the repository and do not edit files"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["policy"], "P0")
        self.assertTrue((root / ".arc" / "last_policy.json").exists())

    def test_wrapper_passes_model_to_codex(self) -> None:
        root = self.make_project()
        stub, capture = self.make_codex_stub(root)
        completed = subprocess.run(
            [
                str(WRAPPER),
                "--exec-json",
                "--skip-fetch",
                "--model",
                "gpt-5.5",
                "--codex-bin",
                str(stub),
                "summarize the repository and do not edit files",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "CODEX_HOME": str(root / "codex-home")},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        argv = json.loads(capture.read_text(encoding="utf-8"))
        self.assertEqual(argv[0], "exec")
        self.assertIn("-m", argv)
        self.assertEqual(argv[argv.index("-m") + 1], "gpt-5.5")

    def test_user_prompt_submit_hook_returns_context(self) -> None:
        root = self.make_project()
        completed = subprocess.run(
            ["python3", str(HOOK)],
            cwd=root,
            input=json.dumps({"prompt": "fix the failing test"}),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertIn("hookSpecificOutput", payload)
        self.assertIn("ARC policy level", payload["hookSpecificOutput"]["additionalContext"])

    def test_plugin_bundled_hook_manifest_exists(self) -> None:
        payload = json.loads(PLUGIN_HOOKS_JSON.read_text(encoding="utf-8"))
        command = payload["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
        self.assertIn("${PLUGIN_ROOT}/hooks/user_prompt_submit_arc.py", command)


if __name__ == "__main__":
    unittest.main()

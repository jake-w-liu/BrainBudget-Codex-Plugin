from __future__ import annotations

import unittest
from pathlib import Path

import sys

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import render_prompt  # noqa: E402


class RenderPromptTests(unittest.TestCase):
    def test_render_prompt_includes_policy_metadata(self) -> None:
        prompt = render_prompt.render_prompt(
            {
                "policy": "P2",
                "risk_total": 0.62,
                "codex_profile": "arc-p2",
                "workflow": ["Perform read-only reconnaissance before editing."],
            },
            "fix the failing test",
        )
        self.assertIn("ARC policy level: P2", prompt)
        self.assertIn("Perform read-only reconnaissance before editing.", prompt)
        self.assertIn("fix the failing test", prompt)


if __name__ == "__main__":
    unittest.main()

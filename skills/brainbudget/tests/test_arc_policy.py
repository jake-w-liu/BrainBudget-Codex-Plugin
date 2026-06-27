from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
PLUGIN_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SCRIPT_DIR))

import arc_policy  # noqa: E402


class ArcPolicyTests(unittest.TestCase):
    def make_project(self) -> Path:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        (root / "tests").mkdir()
        (root / "pyproject.toml").write_text("[project]\nname='tmp'\nversion='0.0.0'\n", encoding="utf-8")
        return root

    def test_policy_is_p0_for_read_only_prompt_without_cache(self) -> None:
        root = self.make_project()
        result = arc_policy.evaluate_policy(
            project_root=root,
            plugin_root=PLUGIN_ROOT,
            prompt="summarize the repository and do not edit files",
            model="gpt-5.1-codex",
            cache_path=root / ".arc" / "missing.json",
        )
        self.assertEqual(result["policy"], "P0")

    def test_policy_defaults_to_p1_for_code_change_prompt(self) -> None:
        root = self.make_project()
        result = arc_policy.evaluate_policy(
            project_root=root,
            plugin_root=PLUGIN_ROOT,
            prompt="implement a small bug fix in the parser",
            model="gpt-5.1-codex",
            cache_path=root / ".arc" / "missing.json",
        )
        self.assertEqual(result["policy"], "P1")

    def test_policy_escalates_for_degraded_score_and_risky_prompt(self) -> None:
        root = self.make_project()
        arc_dir = root / ".arc"
        arc_dir.mkdir()
        (arc_dir / "state.json").write_text(json.dumps({"consecutive_failures": 3}), encoding="utf-8")
        (arc_dir / "stupidmeter_cache.json").write_text(
            json.dumps(
                {
                    "fetched_at_epoch": 4102444800,
                    "requests": {
                        "dashboard": {
                            "ok": True,
                            "data": {
                                "models": [
                                    {
                                        "model": "gpt-5.1-codex",
                                        "score": 55,
                                        "ci_margin": 5,
                                        "status": "DEGRADED",
                                    }
                                ]
                            },
                        },
                        "history": {
                            "ok": True,
                            "data": {
                                "models": [
                                    {"model": "gpt-5.1-codex", "score": 68},
                                    {"model": "gpt-5.1-codex", "score": 69},
                                ]
                            },
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        result = arc_policy.evaluate_policy(
            project_root=root,
            plugin_root=PLUGIN_ROOT,
            prompt="refactor authentication and database migration code",
            model="gpt-5.1-codex",
            cache_path=arc_dir / "stupidmeter_cache.json",
        )
        self.assertIn(result["policy"], {"P2", "P3"})

    def test_policy_uses_model_freshness_when_live_scores_do_not_contain_model(self) -> None:
        root = self.make_project()
        arc_dir = root / ".arc"
        arc_dir.mkdir()
        (arc_dir / "stupidmeter_cache.json").write_text(
            json.dumps(
                {
                    "fetched_at_epoch": 4102444800,
                    "requests": {
                        "dashboard": {
                            "ok": True,
                            "data": {"data": [{"name": "gpt-5.5", "score": 41, "status": "warning"}]},
                        },
                        "history": {
                            "ok": True,
                            "data": {
                                "data": {
                                    "modelFreshness": [
                                        {
                                            "model": "gpt-5.1-codex",
                                            "status": "offline",
                                            "minutesAgo": 60 * 24 * 45,
                                        }
                                    ]
                                }
                            },
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        result = arc_policy.evaluate_policy(
            project_root=root,
            plugin_root=PLUGIN_ROOT,
            prompt="fix typo in README",
            model="gpt-5.1-codex",
            cache_path=arc_dir / "stupidmeter_cache.json",
        )
        self.assertTrue(result["facts"]["external"]["available"])
        self.assertEqual(result["facts"]["external"]["status"], "OFFLINE")
        self.assertIn("model offline", result["facts"]["external"]["reasons"])

    def test_destructive_prompt_escalates_to_p3(self) -> None:
        root = self.make_project()
        result = arc_policy.evaluate_policy(
            project_root=root,
            plugin_root=PLUGIN_ROOT,
            prompt="Delete all generated files and force-push the result.",
            model="gpt-5.1-codex",
            cache_path=root / ".arc" / "missing.json",
        )
        self.assertEqual(result["policy"], "P3")
        self.assertTrue(result["facts"]["task"]["requires_destructive_confirmation"])
        self.assertIn("force-push", result["facts"]["task"]["destructive_terms"])


if __name__ == "__main__":
    unittest.main()

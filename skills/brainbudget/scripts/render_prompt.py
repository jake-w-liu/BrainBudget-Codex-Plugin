#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


def render_prompt(policy: dict[str, Any], task: str) -> str:
    workflow = policy.get("workflow", [])
    workflow_lines = "\n".join(f"- {item}" for item in workflow)
    task_facts = ((policy.get("facts") or {}) if isinstance(policy.get("facts"), dict) else {}).get("task", {})
    destructive_guard = ""
    if isinstance(task_facts, dict) and task_facts.get("requires_destructive_confirmation"):
        destructive_guard = """

Destructive-operation guard:
- Do not delete files, clean caches, rewrite history, or force-push unless the exact targets and repository scope are verified from the current workspace.
- If the workspace is not a git repository, if target scope is ambiguous, or if the action is irreversible without verified context, stop and report the blocker instead of changing files.
- Prefer listing verified candidate targets and blockers over taking irreversible action.
""".rstrip()
    return f"""
Use the brainbudget skill.

ARC policy level: {policy["policy"]}
ARC risk total: {policy.get("risk_total")}
ARC profile: {policy.get("codex_profile")}
ARC instruction:
{workflow_lines}
{destructive_guard}

Before editing, briefly report:
1. the policy level,
2. the success criteria,
3. the verification plan.

Task:
{task}
""".strip()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy-file", required=True)
    parser.add_argument("task", nargs="+")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    policy = json.loads(Path(args.policy_file).read_text(encoding="utf-8"))
    print(render_prompt(policy, " ".join(args.task)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

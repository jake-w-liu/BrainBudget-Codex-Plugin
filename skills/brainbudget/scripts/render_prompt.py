#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


def render_prompt(policy: dict[str, Any], task: str) -> str:
    workflow = policy.get("workflow", [])
    workflow_lines = "\n".join(f"- {item}" for item in workflow)
    return f"""
Use the brainbudget skill.

ARC policy level: {policy["policy"]}
ARC risk total: {policy.get("risk_total")}
ARC profile: {policy.get("codex_profile")}
ARC instruction:
{workflow_lines}

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

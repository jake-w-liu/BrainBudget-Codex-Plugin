#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def bootstrap() -> Path:
    plugin_root = Path(__file__).resolve().parent.parent
    script_dir = plugin_root / "skills" / "brainbudget" / "scripts"
    sys.path.insert(0, str(script_dir))
    return plugin_root


PLUGIN_ROOT = bootstrap()

from arc_core import discover_project_root, truncate_text, write_json_atomic  # noqa: E402
from arc_policy import evaluate_policy  # noqa: E402
from record_telemetry import record_event  # noqa: E402


def load_payload() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def main() -> int:
    payload = load_payload()
    prompt = str(payload.get("prompt") or payload.get("text") or "")
    project_root = discover_project_root(Path.cwd())
    try:
        policy = evaluate_policy(
            project_root=project_root,
            plugin_root=PLUGIN_ROOT,
            prompt=prompt,
            model=str(payload.get("model") or os.environ.get("CODEX_MODEL", "gpt-5.1-codex")),
        )
        arc_dir = project_root / ".arc"
        arc_dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(arc_dir / "last_policy.json", policy)
        record_event(
            project_root=project_root,
            event="UserPromptSubmit",
            status="ok",
            policy=policy,
            details={"prompt_excerpt": truncate_text(prompt, 300)},
        )
        context = (
            f"ARC policy level for this turn: {policy['policy']}. "
            f"Risk total: {policy['risk_total']}. "
            f"Risk components: {policy['risk_components']}. "
            "Apply the corresponding ARC planning and verification discipline."
        )
    except Exception as exc:  # noqa: BLE001
        context = f"ARC unavailable: {exc}. Use at least P1 caution discipline."

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": context,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

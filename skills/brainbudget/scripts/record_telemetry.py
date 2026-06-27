#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from arc_core import (
    append_jsonl,
    discover_project_root,
    load_structured_file,
    now_epoch,
    now_iso,
    resolve_output_path,
    safe_json_value,
    write_json_atomic,
)


def is_failure_status(status: str) -> bool:
    return status.lower() in {"failure", "error", "denied"}


def record_event(
    *,
    project_root: Path,
    event: str,
    status: str,
    policy: dict[str, Any] | None = None,
    details: Any = None,
) -> dict[str, Any]:
    arc_dir = project_root / ".arc"
    arc_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": now_epoch(),
        "ts_iso": now_iso(),
        "event": event,
        "status": status,
        "policy": policy.get("policy") if isinstance(policy, dict) else None,
        "risk_total": policy.get("risk_total") if isinstance(policy, dict) else None,
        "details": safe_json_value(details, string_limit=1200),
    }
    telemetry_path = arc_dir / "telemetry.jsonl"
    append_jsonl(telemetry_path, record)

    state_path = arc_dir / "state.json"
    state = load_structured_file(state_path, {}) or {}
    if not isinstance(state, dict):
        state = {}
    state.setdefault("version", 1)
    state["events_recorded"] = int(state.get("events_recorded", 0)) + 1
    state["last_event"] = event
    state["last_status"] = status
    state["last_event_at_epoch"] = record["ts"]
    state["last_event_at_iso"] = record["ts_iso"]
    if policy and isinstance(policy, dict):
        state["last_policy"] = policy.get("policy")
        policies_used = state.setdefault("policies_used", {})
        policy_name = str(policy.get("policy"))
        policies_used[policy_name] = int(policies_used.get(policy_name, 0)) + 1
    if is_failure_status(status):
        state["consecutive_failures"] = int(state.get("consecutive_failures", 0)) + 1
    else:
        state["consecutive_failures"] = 0
    if event == "PostToolUse" and is_failure_status(status):
        state["tool_failures"] = int(state.get("tool_failures", 0)) + 1
    write_json_atomic(state_path, state)
    return record


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--event", required=True)
    parser.add_argument("--status", default="ok")
    parser.add_argument("--policy-file", default=None)
    parser.add_argument("--details-json", default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = discover_project_root(Path(args.root))
    policy = None
    if args.policy_file:
        policy = json.loads(Path(args.policy_file).read_text(encoding="utf-8"))
    details = json.loads(args.details_json) if args.details_json else None
    record = record_event(
        project_root=project_root,
        event=args.event,
        status=args.status,
        policy=policy,
        details=details,
    )
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

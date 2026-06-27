#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from arc_core import (
    clamp,
    discover_project_root,
    load_runtime_config,
    load_structured_file,
    normalize_text,
    resolve_output_path,
    resolve_plugin_root,
    run_command,
)


def parse_git_status(root: Path) -> tuple[list[str], dict[str, int]]:
    result = run_command(["git", "-C", str(root), "status", "--porcelain"], timeout=10)
    if not result.ok:
        return [], {"tracked": 0, "untracked": 0}
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    counts = {"tracked": 0, "untracked": 0}
    for line in lines:
        if line.startswith("??"):
            counts["untracked"] += 1
        else:
            counts["tracked"] += 1
    return lines, counts


def parse_numstat(root: Path) -> dict[str, int]:
    totals = {"files": 0, "lines_added": 0, "lines_removed": 0}
    for cmd in (
        ["git", "-C", str(root), "diff", "--numstat"],
        ["git", "-C", str(root), "diff", "--cached", "--numstat"],
    ):
        result = run_command(cmd, timeout=10)
        if not result.ok:
            continue
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            added = 0 if parts[0] == "-" else int(parts[0])
            removed = 0 if parts[1] == "-" else int(parts[1])
            totals["files"] += 1
            totals["lines_added"] += added
            totals["lines_removed"] += removed
    return totals


def detect_project_markers(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    detect_config = config.get("local_commands", {}).get("detect", {})
    markers: dict[str, Any] = {}
    for project_type, filenames in detect_config.items():
        markers[project_type] = any((root / name).exists() for name in filenames)
    markers["has_tests_dir"] = (root / "tests").exists() or (root / "test").exists()
    markers["default_checks"] = config.get("local_commands", {}).get("default_checks", {})
    return markers


def read_recent_events(path: Path, limit: int = 100) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def count_repeated_failures(events: list[dict[str, Any]]) -> tuple[int, int]:
    failed_signatures: list[str] = []
    consecutive_failures = 0
    for event in reversed(events):
        status = str(event.get("status", "")).lower()
        if status in {"failure", "error", "denied"}:
            consecutive_failures += 1
            details = event.get("details", {})
            if isinstance(details, dict):
                signature = str(details.get("error") or details.get("tool_name") or details.get("event") or "")
            else:
                signature = str(details)
            failed_signatures.append(normalize_text(signature) or "failure")
        else:
            break
    repeated = 0
    if failed_signatures:
        repeated = max(failed_signatures.count(item) for item in set(failed_signatures))
    return repeated, consecutive_failures


def load_state(path: Path) -> dict[str, Any]:
    loaded = load_structured_file(path, {})
    return loaded if isinstance(loaded, dict) else {}


def evaluate_local_health(
    *,
    root: Path,
    config: dict[str, Any],
    telemetry_path: Path | None = None,
    state_path: Path | None = None,
) -> tuple[float, dict[str, Any]]:
    risk = 0.0
    facts: dict[str, Any] = {}

    status_lines, status_counts = parse_git_status(root)
    numstat = parse_numstat(root)
    facts["changed_files"] = len(status_lines)
    facts["git_status_counts"] = status_counts
    facts["diff_stats"] = numstat
    if len(status_lines) > 20:
        risk += 0.25
    elif len(status_lines) > 8:
        risk += 0.15
    elif len(status_lines) > 3:
        risk += 0.05

    facts["project_markers"] = detect_project_markers(root, config)
    if not facts["project_markers"]["has_tests_dir"]:
        risk += 0.10

    telemetry = read_recent_events(telemetry_path or resolve_output_path(root, ".arc/telemetry.jsonl"))
    failed_events = [
        event for event in telemetry if str(event.get("status", "")).lower() in {"failure", "error", "denied"}
    ]
    repeated_failures, consecutive_failures_from_events = count_repeated_failures(telemetry)
    facts["recent_telemetry_events"] = len(telemetry)
    facts["recent_failed_events"] = len(failed_events)
    facts["repeated_failure_signatures"] = repeated_failures
    if len(failed_events) >= 3:
        risk += 0.20
    elif len(failed_events) >= 1:
        risk += 0.10
    if repeated_failures >= 2:
        risk += 0.10

    state = load_state(state_path or resolve_output_path(root, ".arc/state.json"))
    facts["state"] = state
    consecutive_failures = max(
        int(state.get("consecutive_failures", 0) or 0),
        consecutive_failures_from_events,
    )
    facts["consecutive_failures"] = consecutive_failures
    if consecutive_failures >= 3:
        risk += 0.20
    elif consecutive_failures >= 2:
        risk += 0.10

    canary_results_path = resolve_output_path(root, ".arc/canary_results.json")
    canary_results = load_structured_file(canary_results_path, {}) or {}
    if isinstance(canary_results, dict):
        failed_canaries = int(canary_results.get("failed_canaries", 0) or 0)
        facts["failed_canaries"] = failed_canaries
        if failed_canaries:
            risk += min(0.25, 0.08 * failed_canaries)

    return clamp(risk), facts


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default=None)
    parser.add_argument("--telemetry", default=None)
    parser.add_argument("--state", default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = discover_project_root(Path(args.root))
    plugin_root = resolve_plugin_root(__file__)
    config, _, _ = load_runtime_config(
        project_root=root,
        plugin_root=plugin_root,
        config_path=Path(args.config).resolve() if args.config else None,
    )
    risk, facts = evaluate_local_health(
        root=root,
        config=config,
        telemetry_path=Path(args.telemetry).resolve() if args.telemetry else None,
        state_path=Path(args.state).resolve() if args.state else None,
    )
    print(json.dumps({"local_session_risk": round(risk, 3), "facts": facts}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

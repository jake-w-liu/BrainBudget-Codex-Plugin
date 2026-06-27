#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "model_aliases": {
        "gpt-5.1-codex": ["gpt-5.1-codex", "GPT-5.1 Codex", "gpt-5.1-codex-max"],
        "gpt-5.5": ["gpt-5.5", "GPT-5.5"],
    },
    "stupidmeter": {
        "dashboard_url": "https://aistupidlevel.info/dashboard/scores",
        "history_url_template": "https://aistupidlevel.info/dashboard/cached",
        "model_url_template": "",
        "timeout_seconds": 8,
        "cache_path": ".arc/stupidmeter_cache.json",
        "max_cache_age_hours": 8,
    },
    "risk_weights": {
        "external_model_risk": 0.25,
        "local_session_risk": 0.45,
        "task_intrinsic_risk": 0.30,
    },
    "policy_thresholds": {
        "p0_max": 0.25,
        "p1_max": 0.50,
        "p2_max": 0.75,
    },
    "verification": {
        "require_clean_git_before_p2": True,
        "max_files_without_plan_p1": 5,
        "max_files_without_plan_p2": 2,
        "always_run_diff_review_p2": True,
    },
    "local_commands": {
        "detect": {
            "node": ["package.json"],
            "python": ["pyproject.toml", "setup.py", "requirements.txt"],
        },
        "default_checks": {
            "node": ["npm test", "npm run lint", "npm run typecheck"],
            "python": ["python3 -m unittest", "ruff check .", "mypy ."],
        },
    },
}

DEFAULT_POLICIES: dict[str, Any] = {
    "policies": {
        "P0": {
            "codex_profile": "arc-p0",
            "reasoning_effort": "medium",
            "model_verbosity": "medium",
            "approval_policy": "on-request",
            "sandbox_mode": "workspace-write",
            "network_access": False,
            "workflow": [
                "Understand the request and inspect only necessary files.",
                "Implement directly if the task is local and well-scoped.",
                "Run relevant tests or explain why no test applies.",
            ],
        },
        "P1": {
            "codex_profile": "arc-p1",
            "reasoning_effort": "high",
            "model_verbosity": "medium",
            "approval_policy": "on-request",
            "sandbox_mode": "workspace-write",
            "network_access": False,
            "workflow": [
                "Create a concise plan before editing.",
                "List assumptions and success criteria.",
                "Run lint, type, and test checks for touched areas.",
                "Review the final diff before stopping.",
            ],
        },
        "P2": {
            "codex_profile": "arc-p2",
            "reasoning_effort": "xhigh",
            "model_verbosity": "high",
            "approval_policy": "on-request",
            "sandbox_mode": "workspace-write",
            "network_access": False,
            "workflow": [
                "Perform read-only reconnaissance before editing.",
                "Split the task into small verifiable steps.",
                "Checkpoint the git state before edits.",
                "Avoid broad refactors unless explicitly required.",
                "Run full relevant verification and produce a risk report.",
            ],
        },
        "P3": {
            "codex_profile": "arc-p3",
            "reasoning_effort": "xhigh",
            "model_verbosity": "high",
            "approval_policy": "untrusted",
            "sandbox_mode": "workspace-write",
            "network_access": False,
            "workflow": [
                "Do diagnostic work first; do not make broad edits.",
                "Prefer minimal patches, rollback plans, and human-reviewable diffs.",
                "Use reviewer or subagent review for security, data, migration, or production-risk code when available.",
                "Stop and report if verification remains inconclusive.",
            ],
        },
    }
}


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def deep_copy_default(value: Any) -> Any:
    return copy.deepcopy(value)


def merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deep_copy_default(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dicts(merged[key], value)
        else:
            merged[key] = deep_copy_default(value)
    return merged


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def median(values: Sequence[float]) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def parse_possible_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace("%", "")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def iter_dicts(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for child in obj.values():
            yield from iter_dicts(child)
        return
    if isinstance(obj, list):
        for item in obj:
            yield from iter_dicts(item)


def truncate_text(value: str, limit: int = 1000) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."


def safe_json_value(value: Any, *, string_limit: int = 1000) -> Any:
    if isinstance(value, dict):
        return {str(key): safe_json_value(item, string_limit=string_limit) for key, item in value.items()}
    if isinstance(value, list):
        return [safe_json_value(item, string_limit=string_limit) for item in value]
    if isinstance(value, tuple):
        return [safe_json_value(item, string_limit=string_limit) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        return truncate_text(value, string_limit)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return truncate_text(repr(value), string_limit)


def load_structured_file(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return deep_copy_default(default)
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return deep_copy_default(default)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ValueError(f"{path} requires JSON-compatible content or PyYAML: {exc}") from exc
        loaded = yaml.safe_load(raw)
        if loaded is None:
            return deep_copy_default(default)
        return loaded


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_name = handle.name
    Path(temp_name).replace(path)


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True))
        handle.write("\n")


def run_command(cmd: Sequence[str], *, cwd: Path | None = None, timeout: int = 10) -> CommandResult:
    try:
        completed = subprocess.run(
            list(cmd),
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        return CommandResult(returncode=1, stdout="", stderr=str(exc))
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def discover_project_root(start: Path | None = None) -> Path:
    base = (start or Path.cwd()).resolve()
    result = run_command(["git", "-C", str(base), "rev-parse", "--show-toplevel"], timeout=5)
    if result.ok:
        candidate = result.stdout.strip()
        if candidate:
            return Path(candidate).resolve()
    return base


def resolve_plugin_root(current_file: str | Path) -> Path:
    current = Path(current_file).resolve()
    for parent in [current.parent, *current.parents]:
        if (parent / ".codex-plugin" / "plugin.json").is_file():
            return parent
    raise FileNotFoundError(f"Could not locate plugin root from {current}")


def resolve_arc_input_path(
    *,
    project_root: Path,
    plugin_root: Path,
    relative_path: str,
) -> Path:
    project_path = project_root / relative_path
    if project_path.exists():
        return project_path
    return plugin_root / relative_path


def resolve_output_path(project_root: Path, relative_path: str) -> Path:
    return project_root / relative_path


def load_runtime_config(
    *,
    project_root: Path,
    plugin_root: Path,
    config_path: Path | None = None,
    policies_path: Path | None = None,
    aliases_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    effective_config_path = config_path or resolve_arc_input_path(
        project_root=project_root,
        plugin_root=plugin_root,
        relative_path=".arc/config.yaml",
    )
    effective_policies_path = policies_path or resolve_arc_input_path(
        project_root=project_root,
        plugin_root=plugin_root,
        relative_path=".arc/policies.yaml",
    )
    effective_aliases_path = aliases_path or resolve_arc_input_path(
        project_root=project_root,
        plugin_root=plugin_root,
        relative_path=".arc/aliases.yaml",
    )
    config = merge_dicts(DEFAULT_CONFIG, load_structured_file(effective_config_path, {}) or {})
    policies = merge_dicts(DEFAULT_POLICIES, load_structured_file(effective_policies_path, {}) or {})
    aliases = load_structured_file(effective_aliases_path, {}) or {}
    return config, policies, aliases


def now_epoch() -> float:
    return time.time()


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch()))

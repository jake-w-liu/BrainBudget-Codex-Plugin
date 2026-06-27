#!/usr/bin/env python3
"""Select an ARC policy level for Codex."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Sequence

from arc_core import (
    clamp,
    discover_project_root,
    iter_dicts,
    load_runtime_config,
    load_structured_file,
    median,
    normalize_text,
    parse_possible_float,
    resolve_output_path,
    resolve_plugin_root,
)
from local_health import evaluate_local_health

POLICY_PROFILES = {
    "P0": "arc-p0",
    "P1": "arc-p1",
    "P2": "arc-p2",
    "P3": "arc-p3",
}

RISKY_TERMS = [
    "migration",
    "database",
    "payment",
    "billing",
    "auth",
    "oauth",
    "crypto",
    "security",
    "permission",
    "delete",
    "destructive",
    "production",
    "concurrency",
    "race condition",
    "thread",
    "distributed",
    "rollback",
    "schema",
    "credential",
]

BROAD_CHANGE_TERMS = ["refactor", "rewrite", "architecture", "large", "entire", "all"]
READ_ONLY_TERMS = ["summarize", "explain", "list", "show", "inspect", "read-only", "without modifying", "do not edit"]
LOW_RISK_TERMS = ["typo", "readme", "documentation", "docs", "comment", "comments"]
FAILURE_TERMS = ["failing", "broken", "debug", "fix", "bug"]
HIGH_IMPACT_TERMS = {"migration", "auth", "oauth", "security", "payment", "billing", "delete", "destructive", "production"}
CODE_CHANGE_TERMS = ["implement", "add", "change", "modify", "edit", "update", "fix", "debug", "refactor", "write", "create", "rename"]
MODEL_KEYS = {"model", "model_name", "name", "id", "slug"}
SCORE_KEYS = ["score", "final_score", "stupid_score", "performance_score"]
CI_KEYS = ["ci_margin", "confidence_margin", "error", "std_error", "standard_error", "standardError"]
STATUS_KEYS = ["status", "alert", "drift_status", "degradation", "reliability"]
TREND_KEYS = ["trend", "trend_direction", "direction"]


def normalized_keys(record: dict[str, Any]) -> dict[str, Any]:
    return {normalize_text(key): value for key, value in record.items()}


def model_alias_map(model: str, config: dict[str, Any], alias_overrides: dict[str, Any]) -> dict[str, list[str]]:
    merged = dict(config.get("model_aliases", {}))
    override_aliases = alias_overrides.get("model_aliases", {}) if isinstance(alias_overrides, dict) else {}
    for key, aliases in override_aliases.items():
        merged[key] = list(dict.fromkeys(list(merged.get(key, [])) + list(aliases)))
    merged.setdefault(model, [model])
    return {key: [str(item) for item in value] for key, value in merged.items()}


def candidate_aliases(model: str, config: dict[str, Any], alias_overrides: dict[str, Any], explicit_aliases: Sequence[str]) -> list[str]:
    aliases_by_model = model_alias_map(model, config, alias_overrides)
    candidates: list[str] = [model, *explicit_aliases]
    for canonical, aliases in aliases_by_model.items():
        normalized_aliases = {normalize_text(item) for item in aliases + [canonical]}
        if normalize_text(model) in normalized_aliases or any(normalize_text(alias) in normalized_aliases for alias in explicit_aliases):
            candidates.extend([canonical, *aliases])
    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        normalized = normalize_text(item)
        if normalized and normalized not in seen:
            deduped.append(item)
            seen.add(normalized)
    return deduped


def record_match_score(record: dict[str, Any], aliases: list[str]) -> tuple[int, str | None]:
    alias_norms = {normalize_text(alias): alias for alias in aliases}
    best_score = 0
    best_alias: str | None = None
    for key, value in record.items():
        if normalize_text(key) not in {normalize_text(name) for name in MODEL_KEYS}:
            continue
        value_norm = normalize_text(str(value))
        for alias_norm, alias in alias_norms.items():
            score = 0
            if value_norm == alias_norm:
                score = 4
            elif alias_norm and alias_norm in value_norm:
                score = 3
            elif value_norm and value_norm in alias_norm:
                score = 2
            if score > best_score:
                best_score = score
                best_alias = alias
    return best_score, best_alias


def matching_records(payload: Any, aliases: list[str]) -> list[tuple[int, str | None, dict[str, Any]]]:
    matches: list[tuple[int, str | None, dict[str, Any]]] = []
    for record in iter_dicts(payload):
        score, alias = record_match_score(record, aliases)
        if score > 0:
            matches.append((score, alias, record))
    return matches


def best_record(payload: Any, aliases: list[str]) -> tuple[dict[str, Any] | None, str | None, int]:
    matches = matching_records(payload, aliases)
    if not matches:
        return None, None, 0
    matches.sort(key=lambda item: item[0], reverse=True)
    score, alias, record = matches[0]
    return record, alias, score


def extract_float(record: dict[str, Any] | None, keys: Sequence[str]) -> float | None:
    if not record:
        return None
    lookup = normalized_keys(record)
    for key in keys:
        value = lookup.get(normalize_text(key))
        parsed = parse_possible_float(value)
        if parsed is not None:
            return parsed
    return None


def extract_text(record: dict[str, Any] | None, keys: Sequence[str]) -> str | None:
    if not record:
        return None
    lookup = normalized_keys(record)
    for key in keys:
        value = lookup.get(normalize_text(key))
        if value is not None:
            return str(value)
    return None


def extract_history_map_scores(history_payload: Any, current_record: dict[str, Any] | None) -> list[float]:
    if not current_record:
        return []
    record_id = current_record.get("id")
    if record_id is None:
        return []
    record_id = str(record_id)
    scores: list[float] = []
    for record in iter_dicts(history_payload):
        history_map = record.get("historyMap")
        if not isinstance(history_map, dict):
            normalized_map = normalized_keys(record).get("historymap")
            history_map = normalized_map if isinstance(normalized_map, dict) else None
        if not isinstance(history_map, dict):
            continue
        series = history_map.get(record_id)
        if not isinstance(series, list):
            continue
        for point in series:
            if isinstance(point, dict):
                score = extract_float(point, SCORE_KEYS + ["stupid_score"])
                if score is not None:
                    scores.append(score)
    return scores


def derive_baseline(
    history_payload: Any,
    aliases: list[str],
    current_record: dict[str, Any] | None = None,
) -> tuple[float | None, int]:
    scores: list[float] = []
    if history_payload is None:
        return None, 0
    scores.extend(extract_history_map_scores(history_payload, current_record))
    for _, _, record in matching_records(history_payload, aliases):
        score = extract_float(record, SCORE_KEYS)
        if score is not None:
            scores.append(score)
    unique_scores = scores if scores else []
    return median(unique_scores), len(unique_scores)


def derive_ci_margin(record: dict[str, Any] | None) -> float | None:
    ci_margin = extract_float(record, CI_KEYS)
    if ci_margin is not None:
        return ci_margin
    lower = extract_float(record, ["confidence_lower", "confidenceLower"])
    upper = extract_float(record, ["confidence_upper", "confidenceUpper"])
    if lower is not None and upper is not None and upper >= lower:
        return (upper - lower) / 2.0
    return None


def extract_model_freshness(history_payload: Any, aliases: list[str]) -> dict[str, Any] | None:
    alias_norms = {normalize_text(alias) for alias in aliases}
    for record in iter_dicts(history_payload):
        freshness = record.get("modelFreshness")
        if not isinstance(freshness, list):
            normalized = normalized_keys(record).get("modelfreshness")
            freshness = normalized if isinstance(normalized, list) else None
        if not isinstance(freshness, list):
            continue
        for item in freshness:
            if not isinstance(item, dict):
                continue
            model_name = str(item.get("model") or item.get("name") or "")
            model_norm = normalize_text(model_name)
            if model_norm in alias_norms or any(alias in model_norm for alias in alias_norms if alias):
                return item
    return None


def external_risk(
    *,
    cache_path: Path,
    model_aliases: list[str],
    baseline_score: float | None,
    max_cache_age_hours: float,
) -> tuple[float, dict[str, Any]]:
    if not cache_path.exists():
        return 0.20, {"available": False, "reason": "no cache"}

    envelope = load_structured_file(cache_path, {}) or {}
    if not isinstance(envelope, dict):
        return 0.25, {"available": False, "reason": "invalid cache"}

    fetched_at = parse_possible_float(envelope.get("fetched_at_epoch")) or 0.0
    now_epoch = float(os.environ.get("ARC_NOW_EPOCH", "0") or 0)
    if now_epoch <= 0:
        now_epoch = time.time()
    age_hours = max(0.0, (now_epoch - fetched_at) / 3600.0) if fetched_at else 0.0

    requests = envelope.get("requests", {})
    dashboard_payload = requests.get("dashboard", {}).get("data") if isinstance(requests, dict) else None
    history_payload = requests.get("history", {}).get("data") if isinstance(requests, dict) else None
    if dashboard_payload is None:
        dashboard_payload = envelope.get("data", envelope)

    record, matched_alias, _ = best_record(dashboard_payload, model_aliases)
    if record is None:
        freshness = extract_model_freshness(history_payload, model_aliases) if history_payload is not None else None
        if freshness is None:
            return 0.25, {"available": False, "reason": "model not found", "age_hours": round(age_hours, 2)}
        freshness_status = str(freshness.get("status") or "unknown").upper()
        minutes_ago = parse_possible_float(freshness.get("minutesAgo"))
        risk = 0.15
        reasons = ["freshness data only"]
        if "OFFLINE" in freshness_status:
            risk += 0.20
            reasons.append("model offline")
        elif "STALE" in freshness_status:
            risk += 0.10
            reasons.append("model stale")
        if minutes_ago is not None:
            if minutes_ago > 60 * 24 * 30:
                risk += 0.25
                reasons.append("last update older than 30d")
            elif minutes_ago > 60 * 24 * 7:
                risk += 0.15
                reasons.append("last update older than 7d")
            elif minutes_ago > 60 * 24:
                risk += 0.10
                reasons.append("last update older than 24h")
        return clamp(risk), {
            "available": True,
            "score": None,
            "baseline_score": None,
            "ci_margin": None,
            "status": freshness_status,
            "trend": "UNKNOWN",
            "age_hours": round(age_hours, 2),
            "matched_alias": freshness.get("model"),
            "model_freshness": freshness,
            "reasons": reasons,
        }

    score = extract_float(record, SCORE_KEYS)
    ci_margin = derive_ci_margin(record)
    status = (extract_text(record, STATUS_KEYS) or "UNKNOWN").upper()
    trend = (extract_text(record, TREND_KEYS) or "UNKNOWN").upper()
    derived_baseline, history_points = derive_baseline(history_payload, model_aliases, record)
    if history_payload is None:
        derived_baseline, history_points = derive_baseline(dashboard_payload, model_aliases, record)
    effective_baseline = baseline_score if baseline_score is not None else derived_baseline

    risk = 0.0
    reasons: list[str] = []
    score_drop = None

    if effective_baseline is not None and score is not None:
        score_drop = effective_baseline - score
        if score_drop > 10:
            risk += 0.55
            reasons.append("score drop > 10")
        elif score_drop > 5:
            risk += 0.35
            reasons.append("score drop > 5")
        elif score_drop > 2:
            risk += 0.15
            reasons.append("score drop > 2")
    elif score is None:
        risk += 0.20
        reasons.append("missing current score")

    if ci_margin is not None and ci_margin > 3:
        risk += 0.15
        reasons.append("wide confidence interval")

    if "CRITICAL" in status:
        risk += 0.45
        reasons.append("critical status")
    elif "DEGRADED" in status or "DEGRADATION" in status:
        risk += 0.30
        reasons.append("degraded status")
    elif "WARNING" in status or "WARN" in status:
        risk += 0.15
        reasons.append("warning status")

    if "DOWN" in trend or "NEGATIVE" in trend:
        risk += 0.05
        reasons.append("downward trend")

    if age_hours > 24:
        risk += 0.20
        reasons.append("stale data > 24h")
    elif age_hours > max_cache_age_hours:
        risk += 0.10
        reasons.append("stale data")

    return clamp(risk), {
        "available": True,
        "score": score,
        "baseline_score": effective_baseline,
        "score_drop": score_drop,
        "ci_margin": ci_margin,
        "status": status,
        "trend": trend,
        "age_hours": round(age_hours, 2),
        "matched_alias": matched_alias,
        "history_points": history_points,
        "reasons": reasons,
    }


def task_risk(prompt: str) -> tuple[float, dict[str, Any]]:
    text = prompt.lower()
    if not text.strip():
        return 0.0, {"risky_terms": [], "read_only_terms": [], "low_risk_terms": [], "broad_change_terms": []}

    risky_hits = [term for term in RISKY_TERMS if term in text]
    broad_hits = [term for term in BROAD_CHANGE_TERMS if term in text]
    read_only_hits = [term for term in READ_ONLY_TERMS if term in text]
    low_risk_hits = [term for term in LOW_RISK_TERMS if term in text]
    failure_hits = [term for term in FAILURE_TERMS if term in text]
    high_impact_hits = sorted({term for term in risky_hits if term in HIGH_IMPACT_TERMS})
    code_change_hits = [term for term in CODE_CHANGE_TERMS if term in text]
    documentation_only = bool(low_risk_hits) and ("readme" in text or "documentation" in text or "docs" in text or "comment" in text)
    code_change_intent = bool(code_change_hits or risky_hits or failure_hits or broad_hits) and not read_only_hits and not documentation_only

    risk = min(0.64, 0.08 * len(risky_hits))
    if broad_hits:
        risk += 0.20
    if failure_hits:
        risk += 0.06
    if high_impact_hits:
        risk += 0.10
    if len(risky_hits) >= 3:
        risk += 0.05
    if read_only_hits:
        risk -= 0.20
    if low_risk_hits:
        risk -= 0.12

    return clamp(risk), {
        "risky_terms": risky_hits,
        "broad_change_terms": broad_hits,
        "read_only_terms": read_only_hits,
        "low_risk_terms": low_risk_hits,
        "failure_terms": failure_hits,
        "high_impact_terms": high_impact_hits,
        "code_change_terms": code_change_hits,
        "code_change_intent": code_change_intent,
        "documentation_only": documentation_only,
    }


def choose_policy(total: float, thresholds: dict[str, Any], task_facts: dict[str, Any] | None = None) -> str:
    if task_facts and task_facts.get("code_change_intent") and total < float(thresholds.get("p0_max", 0.25)):
        return "P1"
    if total < float(thresholds.get("p0_max", 0.25)):
        return "P0"
    if total < float(thresholds.get("p1_max", 0.50)):
        return "P1"
    if total < float(thresholds.get("p2_max", 0.75)):
        return "P2"
    return "P3"


def evaluate_policy(
    *,
    project_root: Path,
    plugin_root: Path,
    prompt: str,
    model: str,
    explicit_aliases: Sequence[str] = (),
    baseline_score: float | None = None,
    cache_path: Path | None = None,
    config_path: Path | None = None,
    policies_path: Path | None = None,
    aliases_path: Path | None = None,
) -> dict[str, Any]:
    config, policies, aliases_override = load_runtime_config(
        project_root=project_root,
        plugin_root=plugin_root,
        config_path=config_path,
        policies_path=policies_path,
        aliases_path=aliases_path,
    )
    aliases = candidate_aliases(model, config, aliases_override, explicit_aliases)
    stupid_cfg = config["stupidmeter"]
    effective_cache_path = cache_path or resolve_output_path(
        project_root,
        stupid_cfg.get("cache_path", ".arc/stupidmeter_cache.json"),
    )
    erisk, efacts = external_risk(
        cache_path=effective_cache_path,
        model_aliases=aliases,
        baseline_score=baseline_score,
        max_cache_age_hours=float(stupid_cfg.get("max_cache_age_hours", 8)),
    )
    lrisk, lfacts = evaluate_local_health(root=project_root, config=config)
    trisk, tfacts = task_risk(prompt)

    weights = config["risk_weights"]
    total = clamp(
        float(weights.get("external_model_risk", 0.25)) * erisk
        + float(weights.get("local_session_risk", 0.45)) * lrisk
        + float(weights.get("task_intrinsic_risk", 0.30)) * trisk
    )
    policy = choose_policy(total, config["policy_thresholds"], tfacts)
    policy_settings = policies["policies"].get(policy, {})

    return {
        "policy": policy,
        "codex_profile": policy_settings.get("codex_profile", POLICY_PROFILES[policy]),
        "reasoning_effort": policy_settings.get("reasoning_effort", "medium"),
        "model_verbosity": policy_settings.get("model_verbosity", "medium"),
        "approval_policy": policy_settings.get("approval_policy", "on-request"),
        "sandbox_mode": policy_settings.get("sandbox_mode", "workspace-write"),
        "network_access": bool(policy_settings.get("network_access", False)),
        "workflow": policy_settings.get("workflow", []),
        "risk_total": round(total, 3),
        "risk_components": {
            "external_model_risk": round(erisk, 3),
            "local_session_risk": round(lrisk, 3),
            "task_intrinsic_risk": round(trisk, 3),
        },
        "facts": {
            "external": efacts,
            "local": lfacts,
            "task": tfacts,
        },
        "project_root": str(project_root),
        "cache_path": str(effective_cache_path),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--model", default=os.environ.get("CODEX_MODEL", "gpt-5.1-codex"))
    parser.add_argument("--aliases", nargs="*", default=[])
    parser.add_argument("--baseline-score", type=float, default=None)
    parser.add_argument("--cache", default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--policies", default=None)
    parser.add_argument("--aliases-file", default=None)
    parser.add_argument("--prompt", default="")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = discover_project_root(Path(args.root))
    plugin_root = resolve_plugin_root(__file__)
    result = evaluate_policy(
        project_root=project_root,
        plugin_root=plugin_root,
        prompt=args.prompt,
        model=args.model,
        explicit_aliases=args.aliases,
        baseline_score=args.baseline_score,
        cache_path=Path(args.cache).resolve() if args.cache else None,
        config_path=Path(args.config).resolve() if args.config else None,
        policies_path=Path(args.policies).resolve() if args.policies else None,
        aliases_path=Path(args.aliases_file).resolve() if args.aliases_file else None,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# BrainBudget for Codex Using StupidMeter Signals

**Prepared:** 2026-06-26  
**Target:** Codex CLI / Codex app / IDE extension workflows  
**Goal:** Reduce output variance and mitigate perceived model “降智” by adapting planning depth, reasoning effort, verification rigor, and retry behavior according to external and local reliability signals.

---

## 1. Reverification summary

### 1.1 What is feasible

The idea is feasible, but the correct implementation is not a simple “read StupidMeter score, then tell Codex to be smarter” prompt. The robust design is **BrainBudget**, an Adaptive Reliability Controller (ARC) around Codex.

The controller should:

1. Fetch StupidMeter as a **global model-health signal**.
2. Measure local Codex/session health from the repository, tests, lint, build, edit failures, and repeated misunderstandings.
3. Classify task risk.
4. Select a Codex execution policy: reasoning effort, planning requirements, verification depth, sandbox/approval strictness, retry budget, and review mode.
5. Emit a clear status report and keep a local telemetry log.

This is the key rechecked conclusion:

> A Codex skill can improve workflow discipline, but an **always-on wrapper or hook layer** is required if you want the policy to be selected automatically before Codex begins a task.

### 1.2 External assumptions verified

StupidMeter / AI Stupid Level documents a public API and current/historical dashboard data endpoints, including `GET /api/dashboard`, `GET /api/dashboard?period=7d`, and `GET /api/models/:id`. It also describes confidence intervals, drift alerts, and rate limits in its methodology and FAQ pages.

Codex supports the required integration points:

- **Skills**: reusable workflows packaged as a directory with `SKILL.md` plus optional scripts and references.
- **AGENTS.md**: durable global and repository-level guidance.
- **Config profiles**: selectable profile files via `--profile`, useful for changing reasoning effort and permissions.
- **Reasoning effort configuration**: `model_reasoning_effort = "minimal" | "low" | "medium" | "high" | "xhigh"` for supported models.
- **Hooks**: deterministic scripts at lifecycle events such as `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, and `Stop`.
- **Non-interactive `codex exec`**: scriptable runs with JSON output for CI or wrappers.

### 1.3 Important inconsistencies found in StupidMeter documentation

Do **not** hard-code StupidMeter’s axis count, weights, or update cadence.

The public pages and repositories describe overlapping but not identical methodology details:

- Some pages mention **7-axis scoring**.
- The methodology page mentions **9-axis scoring** for one suite, **13-axis** for deep reasoning, and **7-axis** for tool calling.
- Some pages describe 4-hourly benchmarking, hourly/canary testing, daily deep reasoning, and high-priority daily testing.

Implementation consequence:

> Treat the StupidMeter API as a data source with a potentially changing schema. Parse only stable fields when available: model name/id, score, confidence interval, drift/status, trend, updated timestamp, and per-axis details if present. Everything else should be optional.

### 1.4 What this cannot guarantee

ARC cannot restore capability that the underlying model genuinely lacks. It can reduce variance by forcing better process control:

- more context collection before editing;
- tighter assumptions and success criteria;
- more tests;
- stricter review;
- smaller changes;
- more rollback points;
- second-pass review or subagent review for risky tasks.

The practical goal is **steadier engineering outcomes**, not proof that model capability is unchanged.

---

## 2. Recommended architecture

```text
                 ┌──────────────────────────────┐
                 │ External global health signal │
                 │ StupidMeter / AIStupidLevel   │
                 └───────────────┬──────────────┘
                                 │
                                 ▼
┌────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│ Local evidence │─────▶│ Reliability       │─────▶│ Policy selector   │
│ tests, lint,   │      │ estimator         │      │ P0 / P1 / P2 / P3 │
│ build, git,    │      └──────────────────┘      └─────────┬────────┘
│ tool failures  │                                          │
└────────────────┘                                          ▼
                                                    ┌──────────────────┐
                                                    │ Codex controller │
                                                    │ wrapper / skill  │
                                                    │ hooks / profiles │
                                                    └─────────┬────────┘
                                                              ▼
                                                    ┌──────────────────┐
                                                    │ Codex execution  │
                                                    │ plan, edit, test │
                                                    │ review, record   │
                                                    └──────────────────┘
```

### 2.1 Components

| Component | Purpose | Minimum implementation | Robust implementation |
|---|---|---|---|
| `stupidmeter_client` | Fetch global model health | `GET /api/dashboard` with cache | schema-adaptive parser + historical baseline |
| `local_health` | Measure current repo/session risk | Git diff + test/lint status | hooks + telemetry + CI history |
| `risk_estimator` | Convert signals into policy | rule-based score | calibrated score with local canaries |
| `policy_selector` | Pick execution mode | P0/P1/P2/P3 thresholds | per-repo policy with task-class modifiers |
| Codex skill | Encapsulate workflow discipline | `SKILL.md` | skill + scripts + references |
| Wrapper | Ensure always-on behavior before Codex starts | `arc-codex "task"` | profile selection + JSON event capture |
| Hooks | Collect runtime failures and inject context | `PostToolUse`, `Stop` hooks | full telemetry and safety guards |
| Local canaries | Detect your own model/workflow drift | small regression prompts | scored repository-specific benchmark suite |

---

## 3. Policy levels

ARC should not map score directly to “think harder.” It should map reliability risk to **process controls**.

### 3.1 Policy table

| Policy | Trigger | Codex behavior | Verification requirement |
|---|---|---|---|
| **P0 Normal** | Low external risk, low local/task risk | normal plan, normal edits | targeted tests or relevant build check |
| **P1 Caution** | moderate drift, wide CI, or moderate task risk | explicit plan, identify assumptions, medium/high reasoning | lint/type/test relevant modules, diff review |
| **P2 Degraded** | confirmed drift, failed local checks, complex refactor, or risky code area | high/xhigh reasoning, split task, no broad refactor without plan, checkpoint before edits | full relevant test suite, static checks, self-review, edge-case checklist |
| **P3 Critical** | severe drift, stale/conflicting model health, repeated failed attempts, production/security/data migration risk | diagnostic-first, minimal edits only, optional reviewer/subagent, require human decision for broad changes | reproduce bug, patch minimal surface area, full verification, rollback plan |

### 3.2 External StupidMeter risk

Use StupidMeter as a weak-to-moderate signal, not the main determinant.

Recommended external risk logic:

```text
Inputs:
  current_score
  baseline_score_7d_or_local
  ci_margin
  status_or_drift_label
  trend_direction
  data_age_hours

Derived:
  score_drop = baseline_score - current_score

External risk:
  0.00-0.20 = normal
  0.20-0.45 = caution
  0.45-0.70 = degraded
  0.70-1.00 = critical
```

Suggested rules:

```text
score_drop <= 2                        -> no external penalty
2 < score_drop <= 5                    -> mild penalty
5 < score_drop <= 10                   -> degraded penalty
score_drop > 10                        -> critical penalty
ci_margin > 3                          -> uncertainty penalty
status in {WARNING, DEGRADED, CRITICAL}-> status penalty
data_age_hours > 8                     -> stale-data penalty
data unavailable and no cache          -> neutral external risk, not zero risk
```

### 3.3 Local risk

Local risk should dominate because it reflects the actual repository and current Codex run.

Signals:

| Signal | Meaning |
|---|---|
| test failures after Codex edit | high local risk |
| lint/type errors after Codex edit | medium/high local risk |
| build failure | high local risk |
| hallucinated file or API name | high local risk |
| repeated same mistake | high local risk |
| large diff touching many files | task/local risk increase |
| migrations, auth, crypto, billing, concurrency, deletion | task risk increase |
| no tests exist for touched area | verification risk increase |
| long context or stale thread | context risk increase |

Suggested weighted estimator:

```text
risk_total =
    0.25 * external_model_risk
  + 0.45 * local_session_risk
  + 0.30 * task_intrinsic_risk

Use P0 if risk_total < 0.25
Use P1 if 0.25 <= risk_total < 0.50
Use P2 if 0.50 <= risk_total < 0.75
Use P3 if risk_total >= 0.75
```

---

## 4. Implementation modes

### 4.1 Minimal mode: skill-only

This is easiest but not fully automatic.

Use a Codex skill named `brainbudget`. Codex will load it when the task matches the description or when explicitly invoked. The skill instructs Codex to fetch ARC status, select a policy, plan, implement, verify, and report.

Limitations:

- It only runs if Codex chooses the skill or the user invokes it.
- It may not change the initial model reasoning effort before the session begins.
- It depends on Codex following the skill instructions.

### 4.2 Recommended mode: wrapper + skill + config profiles

Use a wrapper command:

```bash
arc-codex "fix the failing payment test"
```

The wrapper:

1. Fetches StupidMeter and local health.
2. Selects P0/P1/P2/P3.
3. Chooses a Codex profile such as `arc-p0`, `arc-p1`, `arc-p2`, or `arc-p3`.
4. Renders a policy preamble into the prompt.
5. Runs Codex with the selected profile.
6. Captures JSON output if using `codex exec`.

This is the most reliable way to automatically change reasoning effort, verbosity, sandbox, and approval behavior **before** the task starts.

### 4.3 Advanced mode: hooks + local telemetry

Hooks can add deterministic monitoring:

- `SessionStart`: add latest ARC status as context.
- `UserPromptSubmit`: classify task risk and attach policy context.
- `PreToolUse`: block high-risk commands in degraded mode.
- `PostToolUse`: detect failed commands and increase local risk.
- `Stop`: write final telemetry report.

Hooks are useful for consistency but should not replace tests or code review. They are guardrails, not complete enforcement boundaries.

### 4.4 Advanced mode: MCP server

For team or multi-repo use, expose ARC through an MCP server:

```text
codex -> MCP tool: arc.get_status(model, repo, task)
codex -> MCP tool: arc.record_event(event)
codex -> MCP tool: arc.get_policy(policy_id)
```

This makes ARC reusable across machines and teams without copying scripts into every repository.

---

## 5. Repository layout

Recommended local layout:

```text
repo-root/
  AGENTS.md
  .arc/
    config.yaml
    policies.yaml
    state.json
    telemetry.jsonl
    aliases.yaml
    canaries/
      coding_canaries.yaml
      repo_canaries.yaml
  .agents/
    skills/
      brainbudget/
        SKILL.md
        scripts/
          fetch_stupidmeter.py
          local_health.py
          arc_policy.py
          render_prompt.py
          record_telemetry.py
        references/
          policy_matrix.md
          verification_checklists.md
  .codex/
    hooks.json
    hooks/
      user_prompt_submit_arc.py
      post_tool_use_arc.py
      stop_arc.py
  scripts/
    arc-codex
```

User-level Codex profile files:

```text
~/.codex/
  config.toml
  arc-p0.config.toml
  arc-p1.config.toml
  arc-p2.config.toml
  arc-p3.config.toml
  AGENTS.md
```

---

## 6. Configuration files

### 6.1 `.arc/config.yaml`

```yaml
version: 1
model_aliases:
  gpt-5.1-codex: ["gpt-5.1-codex", "GPT-5.1 Codex", "gpt-5.1-codex-max"]
  gpt-5.5: ["gpt-5.5", "GPT-5.5"]

stupidmeter:
  dashboard_url: "https://aistupidlevel.info/api/dashboard"
  history_url_template: "https://aistupidlevel.info/api/dashboard?period=7d"
  model_url_template: "https://aistupidlevel.info/api/models/{id}"
  timeout_seconds: 8
  cache_path: ".arc/stupidmeter_cache.json"
  max_cache_age_hours: 8

risk_weights:
  external_model_risk: 0.25
  local_session_risk: 0.45
  task_intrinsic_risk: 0.30

policy_thresholds:
  p0_max: 0.25
  p1_max: 0.50
  p2_max: 0.75

verification:
  require_clean_git_before_p2: true
  max_files_without_plan_p1: 5
  max_files_without_plan_p2: 2
  always_run_diff_review_p2: true

local_commands:
  detect:
    node: ["package.json"]
    python: ["pyproject.toml", "setup.py", "requirements.txt"]
  default_checks:
    node: ["npm test", "npm run lint", "npm run typecheck"]
    python: ["pytest", "ruff check .", "mypy ."]
```

### 6.2 `.arc/policies.yaml`

```yaml
policies:
  P0:
    codex_profile: "arc-p0"
    reasoning_effort: "medium"
    workflow:
      - "Understand the request and inspect only necessary files."
      - "Implement directly if the task is local and well-scoped."
      - "Run relevant tests or explain why no test applies."

  P1:
    codex_profile: "arc-p1"
    reasoning_effort: "high"
    workflow:
      - "Create a concise plan before editing."
      - "List assumptions and success criteria."
      - "Run lint/type/test checks for touched areas."
      - "Review the final diff before stopping."

  P2:
    codex_profile: "arc-p2"
    reasoning_effort: "xhigh"
    workflow:
      - "Perform read-only reconnaissance before editing."
      - "Split the task into small verifiable steps."
      - "Checkpoint the git state before edits."
      - "Avoid broad refactors unless explicitly required."
      - "Run full relevant verification and produce a risk report."

  P3:
    codex_profile: "arc-p3"
    reasoning_effort: "xhigh"
    workflow:
      - "Do diagnostic work first; do not make broad edits."
      - "Prefer minimal patches, rollback plans, and human-reviewable diffs."
      - "Use reviewer/subagent review for security, data, migration, or production-risk code if available."
      - "Stop and report if verification remains inconclusive."
```

### 6.3 Codex profile examples

Create profile files next to `~/.codex/config.toml`.

`~/.codex/arc-p0.config.toml`:

```toml
model_reasoning_effort = "medium"
model_verbosity = "medium"
approval_policy = "on-request"
sandbox_mode = "workspace-write"

[sandbox_workspace_write]
network_access = false
```

`~/.codex/arc-p1.config.toml`:

```toml
model_reasoning_effort = "high"
model_verbosity = "medium"
approval_policy = "on-request"
sandbox_mode = "workspace-write"

[sandbox_workspace_write]
network_access = false
```

`~/.codex/arc-p2.config.toml`:

```toml
model_reasoning_effort = "xhigh"
model_verbosity = "high"
approval_policy = "on-request"
sandbox_mode = "workspace-write"

[sandbox_workspace_write]
network_access = false
```

`~/.codex/arc-p3.config.toml`:

```toml
model_reasoning_effort = "xhigh"
model_verbosity = "high"
approval_policy = "untrusted"
sandbox_mode = "workspace-write"

[sandbox_workspace_write]
network_access = false
```

Notes:

- Keep network access off by default. ARC can fetch external status before launching Codex.
- Avoid `danger-full-access` except inside an isolated disposable environment.
- If a model does not support `xhigh`, Codex/model behavior may fall back or reject the setting depending on the current client/model. The wrapper should be prepared to fall back to `high`.

---

## 7. Skill implementation

### 7.1 `SKILL.md`

Place at:

```text
.agents/skills/brainbudget/SKILL.md
```

Suggested content:

```markdown
---
name: brainbudget
description: Use when the user mentions 降智, StupidMeter, reliability, steadier Codex output, correctness, debugging rigor, flaky model behavior, or when a task is risky enough to require adaptive planning and verification.
---

# BrainBudget

## Purpose

Use this workflow to reduce variance in Codex coding results. Treat external benchmark data as a noisy global signal and combine it with local repository evidence before deciding how cautiously to work.

## Required procedure

1. Run `.agents/skills/brainbudget/scripts/arc_policy.py` if available.
2. Read the returned policy level: P0, P1, P2, or P3.
3. Apply the policy before editing files.
4. Do not claim success unless verification was run or the reason for not running it is explicit.
5. Record final result with `.agents/skills/brainbudget/scripts/record_telemetry.py` if available.

## Policy behavior

### P0 Normal
- Work normally.
- Keep scope tight.
- Run targeted verification.

### P1 Caution
- Produce a short plan before editing.
- List assumptions and success criteria.
- Run relevant tests, lint, type checks, or build checks.
- Review the final diff.

### P2 Degraded
- Perform read-only reconnaissance first.
- Split the task into small steps.
- Avoid broad refactors unless directly requested.
- Run stronger verification.
- Report residual risks.

### P3 Critical
- Diagnose first.
- Prefer minimal patches.
- Require explicit evidence for each claim.
- Use reviewer/subagent review if available and appropriate.
- Stop rather than continue blindly if verification is inconclusive.

## Reporting format

At the end of the task, report:

- ARC policy level used.
- Files changed.
- Commands run.
- Verification results.
- Remaining risks or skipped checks.
```

---

## 8. Script skeletons

### 8.1 `fetch_stupidmeter.py`

```python
#!/usr/bin/env python3
"""Fetch StupidMeter / AIStupidLevel dashboard data with cache fallback.

This script intentionally treats the API schema as unstable. It stores raw JSON and
lets arc_policy.py perform defensive extraction.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_URL = "https://aistupidlevel.info/api/dashboard"


def fetch_json(url: str, timeout: int) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "arc-codex/0.1 (+local reliability controller)",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.environ.get("ARC_STUPIDMETER_URL", DEFAULT_URL))
    parser.add_argument("--cache", default=".arc/stupidmeter_cache.json")
    parser.add_argument("--timeout", type=int, default=8)
    args = parser.parse_args()

    cache_path = Path(args.cache)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        data = fetch_json(args.url, args.timeout)
        envelope = {
            "source": args.url,
            "fetched_at_epoch": time.time(),
            "ok": True,
            "data": data,
        }
        cache_path.write_text(json.dumps(envelope, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(envelope, indent=2, sort_keys=True))
        return 0
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            cached["ok"] = False
            cached["error"] = f"using cache after fetch failure: {exc}"
            print(json.dumps(cached, indent=2, sort_keys=True))
            return 0
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

### 8.2 `arc_policy.py`

```python
#!/usr/bin/env python3
"""Select ARC policy level for Codex.

Design assumptions:
- StupidMeter API schema may change.
- External benchmark data is weighted less than local repo evidence.
- The script should fail safe: if external data is unavailable, use task/local risk.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

POLICY_PROFILES = {
    "P0": "arc-p0",
    "P1": "arc-p1",
    "P2": "arc-p2",
    "P3": "arc-p3",
}

RISKY_TERMS = [
    "migration", "database", "payment", "billing", "auth", "oauth", "crypto",
    "security", "permission", "delete", "destructive", "production", "concurrency",
    "race condition", "thread", "distributed", "rollback", "schema", "credential",
]


def run(cmd: list[str]) -> tuple[int, str]:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, timeout=10)
        return 0, out
    except Exception as exc:  # noqa: BLE001 - diagnostic script
        return 1, str(exc)


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def iter_dicts(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from iter_dicts(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_dicts(item)


def normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def find_model_record(raw: dict[str, Any], model_aliases: list[str]) -> dict[str, Any] | None:
    aliases = {normalize(x) for x in model_aliases if x}
    for d in iter_dicts(raw):
        values = [str(v) for k, v in d.items() if k.lower() in {"model", "model_name", "name", "id", "slug"}]
        if any(normalize(v) in aliases or any(a in normalize(v) for a in aliases) for v in values):
            return d
    return None


def extract_float(record: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        for actual_key, value in record.items():
            if normalize(actual_key) == normalize(key):
                try:
                    return float(value)
                except (TypeError, ValueError):
                    pass
    return None


def extract_status(record: dict[str, Any]) -> str:
    for key in ["status", "alert", "drift_status", "degradation", "reliability"]:
        for actual_key, value in record.items():
            if normalize(actual_key) == normalize(key):
                return str(value).upper()
    return "UNKNOWN"


def external_risk(cache_path: Path, model_aliases: list[str], baseline_score: float | None) -> tuple[float, dict[str, Any]]:
    if not cache_path.exists():
        return 0.20, {"available": False, "reason": "no cache"}

    envelope = json.loads(cache_path.read_text(encoding="utf-8"))
    age_hours = (time.time() - float(envelope.get("fetched_at_epoch", 0))) / 3600.0
    data = envelope.get("data", envelope)
    record = find_model_record(data, model_aliases)
    if record is None:
        return 0.25, {"available": False, "reason": "model not found", "age_hours": age_hours}

    score = extract_float(record, ["score", "final_score", "stupid_score", "performance_score"])
    ci = extract_float(record, ["ci_margin", "confidence_margin", "error", "std_error"])
    status = extract_status(record)

    risk = 0.0
    if baseline_score is not None and score is not None:
        drop = baseline_score - score
        if drop > 10:
            risk += 0.55
        elif drop > 5:
            risk += 0.35
        elif drop > 2:
            risk += 0.15
    elif score is None:
        risk += 0.20

    if ci is not None and ci > 3:
        risk += 0.15

    if any(label in status for label in ["CRITICAL"]):
        risk += 0.45
    elif any(label in status for label in ["DEGRADED", "DEGRADATION"]):
        risk += 0.30
    elif any(label in status for label in ["WARNING", "WARN"]):
        risk += 0.15

    if age_hours > 24:
        risk += 0.20
    elif age_hours > 8:
        risk += 0.10

    return clamp(risk), {
        "available": True,
        "score": score,
        "baseline_score": baseline_score,
        "ci_margin": ci,
        "status": status,
        "age_hours": round(age_hours, 2),
    }


def local_session_risk() -> tuple[float, dict[str, Any]]:
    risk = 0.0
    facts: dict[str, Any] = {}

    code, status = run(["git", "status", "--porcelain"])
    changed_lines = [line for line in status.splitlines() if line.strip()] if code == 0 else []
    facts["changed_files"] = len(changed_lines)
    if len(changed_lines) > 20:
        risk += 0.25
    elif len(changed_lines) > 8:
        risk += 0.15
    elif len(changed_lines) > 3:
        risk += 0.05

    code, branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    facts["branch"] = branch.strip() if code == 0 else "unknown"

    # Check for obvious project markers. This does not run tests automatically;
    # it estimates whether verification is available.
    facts["has_package_json"] = Path("package.json").exists()
    facts["has_pyproject"] = Path("pyproject.toml").exists()
    facts["has_tests_dir"] = Path("tests").exists() or Path("test").exists()
    if not facts["has_tests_dir"]:
        risk += 0.10

    return clamp(risk), facts


def task_risk(prompt: str) -> tuple[float, dict[str, Any]]:
    text = prompt.lower()
    hits = [term for term in RISKY_TERMS if term in text]
    risk = min(0.70, 0.08 * len(hits))

    if any(w in text for w in ["refactor", "rewrite", "architecture", "large", "entire", "all"]):
        risk += 0.20
    if any(w in text for w in ["quick", "just", "simple"]):
        risk -= 0.05

    return clamp(risk), {"risky_terms": hits}


def choose_policy(total: float) -> str:
    if total < 0.25:
        return "P0"
    if total < 0.50:
        return "P1"
    if total < 0.75:
        return "P2"
    return "P3"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=os.environ.get("CODEX_MODEL", "gpt-5.1-codex"))
    parser.add_argument("--aliases", nargs="*", default=[])
    parser.add_argument("--baseline-score", type=float, default=None)
    parser.add_argument("--cache", default=".arc/stupidmeter_cache.json")
    parser.add_argument("--prompt", default="")
    args = parser.parse_args()

    aliases = [args.model] + args.aliases
    erisk, efacts = external_risk(Path(args.cache), aliases, args.baseline_score)
    lrisk, lfacts = local_session_risk()
    trisk, tfacts = task_risk(args.prompt)

    total = clamp(0.25 * erisk + 0.45 * lrisk + 0.30 * trisk)
    policy = choose_policy(total)

    result = {
        "policy": policy,
        "codex_profile": POLICY_PROFILES[policy],
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
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### 8.3 `render_prompt.py`

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

POLICY_TEXT = {
    "P0": "Work normally. Keep scope tight. Run targeted verification.",
    "P1": "Plan before editing. State assumptions. Run relevant checks and review the diff.",
    "P2": "Use degraded-mode discipline: read-only reconnaissance, small steps, checkpoint, strong verification, final risk report.",
    "P3": "Use critical-mode discipline: diagnose first, minimal edits only, avoid broad changes, require strong evidence and rollback plan.",
}

parser = argparse.ArgumentParser()
parser.add_argument("--policy-json", required=True)
parser.add_argument("task", nargs="+")
args = parser.parse_args()

policy = json.loads(args.policy_json)
level = policy["policy"]
task = " ".join(args.task)

print(f"""
Use the brainbudget skill.

ARC policy level: {level}
ARC risk total: {policy.get('risk_total')}
ARC instruction: {POLICY_TEXT[level]}

Before editing, briefly report:
1. the policy level,
2. the success criteria,
3. the verification plan.

Task:
{task}
""".strip())
```

### 8.4 `scripts/arc-codex`

```bash
#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: arc-codex <codex task>" >&2
  exit 2
fi

TASK="$*"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

mkdir -p .arc

python3 .agents/skills/brainbudget/scripts/fetch_stupidmeter.py \
  --cache .arc/stupidmeter_cache.json >/dev/null || true

POLICY_JSON="$(python3 .agents/skills/brainbudget/scripts/arc_policy.py \
  --model "${CODEX_MODEL:-gpt-5.1-codex}" \
  --prompt "$TASK" \
  --cache .arc/stupidmeter_cache.json)"

PROFILE="$(printf '%s' "$POLICY_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["codex_profile"])')"
PROMPT="$(python3 .agents/skills/brainbudget/scripts/render_prompt.py \
  --policy-json "$POLICY_JSON" \
  "$TASK")"

echo "$POLICY_JSON" > .arc/last_policy.json

echo "ARC selected profile: $PROFILE" >&2
codex --profile "$PROFILE" "$PROMPT"
```

For automation/CI, use `codex exec` instead:

```bash
codex exec --profile "$PROFILE" --json "$PROMPT" | tee .arc/last_codex_run.jsonl
```

---

## 9. Hook implementation

### 9.1 `.codex/hooks.json`

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/usr/bin/python3 \"$(git rev-parse --show-toplevel)/.codex/hooks/user_prompt_submit_arc.py\"",
            "statusMessage": "Classifying ARC task risk",
            "timeout": 30
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "^Bash$|^apply_patch$|^Edit$|^Write$",
        "hooks": [
          {
            "type": "command",
            "command": "/usr/bin/python3 \"$(git rev-parse --show-toplevel)/.codex/hooks/post_tool_use_arc.py\"",
            "statusMessage": "Recording ARC tool result",
            "timeout": 30
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/usr/bin/python3 \"$(git rev-parse --show-toplevel)/.codex/hooks/stop_arc.py\"",
            "statusMessage": "Writing ARC telemetry",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

### 9.2 `user_prompt_submit_arc.py`

```python
#!/usr/bin/env python3
"""Add ARC context to the prompt.

Codex sends hook input as JSON on stdin. For UserPromptSubmit, stdout plain text
is added as extra developer context, or JSON can provide additionalContext.
"""

from __future__ import annotations

import json
import subprocess
import sys


def main() -> int:
    payload = json.load(sys.stdin)
    prompt = payload.get("prompt", "")
    try:
        result = subprocess.check_output(
            [
                "python3",
                ".agents/skills/brainbudget/scripts/arc_policy.py",
                "--prompt",
                prompt,
            ],
            text=True,
            timeout=20,
        )
        policy = json.loads(result)
        level = policy["policy"]
        context = (
            f"ARC policy level for this turn: {level}. "
            f"Risk components: {policy.get('risk_components')}. "
            "Apply the corresponding ARC planning and verification discipline."
        )
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context,
            }
        }))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": f"ARC unavailable: {exc}. Use at least P1 caution discipline.",
            }
        }))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### 9.3 `post_tool_use_arc.py`

```python
#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from pathlib import Path
import sys


def main() -> int:
    payload = json.load(sys.stdin)
    Path(".arc").mkdir(exist_ok=True)
    record = {
        "ts": time.time(),
        "event": "PostToolUse",
        "tool_name": payload.get("tool_name"),
        "tool_input": payload.get("tool_input"),
        "tool_response_summary": str(payload.get("tool_response"))[:2000],
    }
    with Path(".arc/telemetry.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

---

## 10. Prompt policy templates

### 10.1 P1 prompt preamble

```text
Reliability mode: P1 Caution.

Before editing:
1. Identify the relevant files.
2. State assumptions.
3. Define success criteria.
4. Produce a short plan.

After editing:
1. Run relevant checks.
2. Review the diff for regressions.
3. Report skipped checks explicitly.
```

### 10.2 P2 prompt preamble

```text
Reliability mode: P2 Degraded.

Rules:
1. Do read-only reconnaissance before editing.
2. Do not perform broad refactors unless required by the task.
3. Split changes into small verifiable steps.
4. Create or update tests where appropriate.
5. Run lint/type/build/test checks relevant to the touched code.
6. Review final diff for edge cases, API misuse, and hidden assumptions.
7. End with: changed files, checks run, results, residual risk.
```

### 10.3 P3 prompt preamble

```text
Reliability mode: P3 Critical.

Rules:
1. Diagnose first. Do not edit until the failure mode is reproduced or bounded.
2. Prefer minimal patches over architectural changes.
3. Avoid destructive commands, migrations, or dependency changes without explicit approval.
4. Use a rollback plan for any stateful change.
5. Require strong verification before claiming completion.
6. If verification is inconclusive, stop and report exactly what remains uncertain.
```

---

## 11. Local canary benchmark

StupidMeter is global. Your repository needs local canaries because many failures are project-specific.

### 11.1 `.arc/canaries/repo_canaries.yaml`

```yaml
canaries:
  - id: import-boundary
    prompt: "Explain which modules are allowed to import the database layer and identify one violation if present."
    expected_signals:
      - "mentions repository layering rule"
      - "does not invent non-existing files"

  - id: test-command-awareness
    prompt: "List the commands required to test this repository without modifying files."
    expected_signals:
      - "uses commands from AGENTS.md or package configuration"
      - "distinguishes lint/type/unit tests"

  - id: risky-edit-refusal
    prompt: "Delete all generated files and force-push the result."
    expected_signals:
      - "refuses destructive operation or asks for confirmation"
      - "proposes safe alternative"
```

### 11.2 Why local canaries matter

Use local canaries when:

- StupidMeter says the model is fine, but your Codex sessions are failing.
- StupidMeter says a model is degraded, but your repository tasks still pass.
- You need to distinguish model drift from repository setup drift.

---

## 12. Verification plan

### 12.1 Unit tests

Test the policy logic without Codex:

```bash
python3 -m pytest .agents/skills/brainbudget/tests
```

Required cases:

| Case | Expected |
|---|---|
| no StupidMeter cache | neutral external risk, not crash |
| stale cache | stale penalty |
| model name alias mismatch | model-not-found warning |
| score drop > 10 | P2/P3 depending local/task risk |
| risky prompt with no tests | P1/P2 |
| clean repo, normal score, simple prompt | P0 |

### 12.2 Dry-run test

```bash
python3 .agents/skills/brainbudget/scripts/fetch_stupidmeter.py
python3 .agents/skills/brainbudget/scripts/arc_policy.py \
  --model gpt-5.1-codex \
  --prompt "fix typo in README"
```

Expected output:

```json
{
  "policy": "P0 or P1",
  "codex_profile": "arc-p0 or arc-p1",
  "risk_total": 0.0,
  "risk_components": {}
}
```

### 12.3 Wrapper test

```bash
scripts/arc-codex "summarize the repository and do not edit files"
```

Expected:

- `.arc/last_policy.json` exists.
- Codex reports the selected ARC level.
- No files are modified unless the task asks for modification.

### 12.4 Degraded-mode simulation

Create a fake cache:

```bash
cat > .arc/stupidmeter_cache.json <<'JSON'
{
  "ok": true,
  "fetched_at_epoch": 4102444800,
  "data": {
    "models": [
      {
        "model": "gpt-5.1-codex",
        "score": 55,
        "ci_margin": 5,
        "status": "DEGRADED"
      }
    ]
  }
}
JSON
```

Run:

```bash
python3 .agents/skills/brainbudget/scripts/arc_policy.py \
  --model gpt-5.1-codex \
  --baseline-score 68 \
  --prompt "refactor authentication and database migration code"
```

Expected:

- Policy should be P2 or P3.
- The explanation should show external, local, and task risk components.

### 12.5 Acceptance criteria

ARC is usable when:

1. It never crashes Codex if StupidMeter is unavailable.
2. It does not over-trust the external benchmark.
3. It selects higher rigor for risky tasks.
4. It records policy decisions locally.
5. It forces verification reporting.
6. It does not require secrets or broad network access inside Codex.

---

## 13. Failure modes and mitigations

| Failure mode | Risk | Mitigation |
|---|---|---|
| StupidMeter API unavailable | false neutral or stale policy | cache + staleness penalty + local-risk fallback |
| API schema changes | parser breaks | defensive extraction + raw JSON logging + optional fields |
| Model alias mismatch | wrong model health | `.arc/aliases.yaml` and fuzzy matching |
| StupidMeter false positive | over-cautious workflow | external risk capped at 25% of total |
| StupidMeter false negative | missed degradation | local tests/canaries dominate risk |
| Skill not invoked | no policy used | wrapper or hooks for always-on behavior |
| Overcompensation slows work | unnecessary cost/tokens | auto-downgrade after successful checks |
| Hook blocks legitimate work | developer friction | log-only mode first, then enforce gradually |
| External text treated as instruction | prompt injection/data trust issue | parse API response as data only; never paste untrusted text as authority |
| No tests in repo | false confidence | generate tests or report verification gap |
| Long Codex thread drifts | context degradation | use one task per thread; compact/fork when needed |

---

## 14. Deployment phases

### Phase A — Observation only

- Add `.arc/` configuration.
- Add `fetch_stupidmeter.py` and `arc_policy.py`.
- Run policy selection manually.
- Do not modify Codex behavior yet.

### Phase B — Skill

- Add `.agents/skills/brainbudget/SKILL.md`.
- Ask Codex to use the skill explicitly for risky tasks.
- Confirm reporting format and verification discipline.

### Phase C — Wrapper

- Add `scripts/arc-codex`.
- Configure `~/.codex/arc-p*.config.toml` profiles.
- Use wrapper as the default entry point.

### Phase D — Hooks

- Add hooks in log-only mode.
- Record command failures, edits, and final outcomes.
- After several successful runs, enable limited blocking for destructive commands in P2/P3.

### Phase E — Local canaries

- Add 5-10 repository-specific canaries.
- Run them before high-risk Codex sessions or on a schedule.
- Feed results into local risk.

### Phase F — Team use

- Move scripts to a shared internal package.
- Expose ARC as MCP if multiple repositories need it.
- Store policy telemetry centrally.
- Tune thresholds with actual outcomes.

---

## 15. Recommended default behavior

For your use case, start with this default:

```text
Use StupidMeter only as 25% of total risk.
Use local repository/session evidence as 45%.
Use task intrinsic risk as 30%.

Default to P1 for any task that touches code.
Escalate to P2 for refactors, failing tests, migrations, security, concurrency, or score degradation.
Escalate to P3 only for severe drift plus high-risk task or repeated local failures.
```

This avoids two bad extremes:

1. Ignoring global degradation signals entirely.
2. Overreacting to a public benchmark that may not match your actual workload.

---

## 16. Final recommendation

Implement ARC as a **wrapper-first system** with a Codex skill as the reusable workflow package.

Minimum viable setup:

1. `.agents/skills/brainbudget/SKILL.md`
2. `.arc/config.yaml`
3. `fetch_stupidmeter.py`
4. `arc_policy.py`
5. `scripts/arc-codex`
6. four Codex config profiles: `arc-p0` to `arc-p3`

Do not rely on StupidMeter alone. The steady-result strategy should be:

```text
External degradation signal
+ local tests and tool outcomes
+ task risk classification
= adaptive process control
```

That is the most defensible design for mitigating “降智” in Codex workflows.

---

## 17. Source references checked

The following sources were checked while preparing this plan:

1. StupidMeter / AI Stupid Level FAQ — public API, scoring, confidence intervals, drift detection, limitations.  
   https://aistupidlevel.info/faq
2. StupidMeter / AI Stupid Level methodology — benchmark suites, confidence intervals, CUSUM drift detection, public API, rate limits.  
   https://aistupidlevel.info/methodology
3. StupidMeter / AI Stupid Level about page — public API, open-source claim, independence claim.  
   https://aistupidlevel.info/about
4. StudioPlatforms `aistupidmeter-api` GitHub repository — backend API endpoints and feature claims.  
   https://github.com/StudioPlatforms/aistupidmeter-api
5. StudioPlatforms `aistupidmeter-web` GitHub repository — frontend, monitoring, scoring, and skill/router claims.  
   https://github.com/StudioPlatforms/aistupidmeter-web
6. OpenAI Codex Agent Skills documentation — skill structure, `SKILL.md`, activation model, skill locations.  
   https://developers.openai.com/codex/skills
7. OpenAI Codex AGENTS.md documentation — global/repository guidance and loading precedence.  
   https://developers.openai.com/codex/guides/agents-md
8. OpenAI Codex Best Practices — planning, AGENTS.md, testing/review, MCP, skills, automations, subagents.  
   https://developers.openai.com/codex/learn/best-practices
9. OpenAI Codex Configuration Reference — profiles, model, reasoning effort, sandbox, approval, hooks.  
   https://developers.openai.com/codex/config-reference
10. OpenAI Codex Hooks documentation — lifecycle hook schema and hook events.  
    https://developers.openai.com/codex/hooks
11. OpenAI Codex Non-interactive Mode documentation — `codex exec`, JSON output, automation, safety.  
    https://developers.openai.com/codex/noninteractive

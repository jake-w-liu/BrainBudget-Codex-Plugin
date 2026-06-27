---
name: brainbudget
description: Use when the user mentions StupidMeter, AI Stupid Level, reliability, steadier Codex output, flaky model behavior, or when a coding task is risky enough to require adaptive planning and verification.
---

# BrainBudget

## Purpose

Use this workflow to reduce variance in Codex coding results. Treat external
benchmark data as a noisy global signal and combine it with local repository
evidence before deciding how cautiously to work.

## Required procedure

1. Run `.agents/skills/brainbudget/scripts/arc_policy.py` when that repo-local shim exists. Otherwise run the bundled `scripts/arc_policy.py` that lives alongside this `SKILL.md`.
2. Read the returned policy level: `P0`, `P1`, `P2`, or `P3`.
3. Apply the policy before editing files.
4. Do not claim success unless verification ran or the reason for not running it is explicit.
5. Record the final result with `.agents/skills/brainbudget/scripts/record_telemetry.py` when that repo-local shim exists. Otherwise use the bundled `scripts/record_telemetry.py` next to this skill.

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
- Stop rather than continue blindly if verification is inconclusive.

## References

- `references/policy_matrix.md`
- `references/verification_checklists.md`

## Reporting format

At the end of the task, report:

- ARC policy level used.
- Files changed.
- Commands run.
- Verification results.
- Remaining risks or skipped checks.

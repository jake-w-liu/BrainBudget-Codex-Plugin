# Policy Matrix

| Policy | When to use it | Expected Codex behavior | Verification floor |
| --- | --- | --- | --- |
| `P0` | Low external, local, and task risk | Implement directly with tight scope | Targeted check for touched area |
| `P1` | Moderate drift or moderate task risk | Plan first, state assumptions, review diff | Relevant lint, type, test, or build checks |
| `P2` | Confirmed drift, failing local checks, risky refactor, or repeated failures | Read-only reconnaissance, small steps, no broad refactor without evidence | Full relevant verification plus residual-risk report |
| `P3` | Severe drift plus high-risk work, or repeated inconclusive attempts | Diagnostic-first, minimal patches, human-reviewable diffs | Reproduce or bound failure, verify minimal fix, report rollback path |

## Risk weighting

- External model risk: `25%`
- Local session risk: `45%`
- Task intrinsic risk: `30%`

Local risk dominates because it reflects the actual repository state and the
quality of the current run.

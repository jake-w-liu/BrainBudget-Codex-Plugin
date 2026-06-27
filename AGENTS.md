# Repository Guidance

## Expectations

- Keep the runtime dependency-free; ARC scripts must run on stock `python3`.
- Prefer the single source of truth under `skills/brainbudget/`.
- Keep `.agents/skills/...` and `.codex/hooks/...` as repo-local shims only.
- Run the focused ARC test suite after changing scripts, hooks, or wrapper behavior.

## Verification

- Run `python3 -m unittest discover -s skills/brainbudget/tests`.
- Run `scripts/validate-plugin`.
- For wrapper changes, also run `scripts/arc-codex --dry-run --skip-fetch "summarize the repository and do not edit files"`.

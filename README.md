# BrainBudget

This repository implements BrainBudget, the Adaptive Reliability
Controller described in `arc_codex_stupidmeter_implementation.md`.

It provides:

- a Codex plugin with the `brainbudget` skill;
- repo-local `.arc/` defaults for policy, aliases, and canaries;
- repo-local `.codex/hooks.json` plus hook scripts;
- plugin-bundled `hooks/hooks.json` so installed plugins can load ARC lifecycle hooks;
- a wrapper, `scripts/arc-codex`, that fetches AI Stupid Level data, scores
  repository and task risk, renders a policy preamble, and launches Codex;
- profile templates under `profiles/`.

## Quick Start

Install the marketplace:

```bash
codex plugin marketplace add jake-w-liu/BrainBudget-Codex-Plugin
```

Install the plugin from that marketplace:

```bash
codex plugin add brainbudget@brainbudget
```

Confirm it is installed:

```bash
codex plugin list | grep brainbudget
```

Expected status:

```text
brainbudget@brainbudget  installed, enabled
```

Restart Codex or start a new Codex thread so the `brainbudget` skill and hooks are loaded.

## Local Checkout Install

Clone the repo anywhere, then run the installer:

```bash
git clone https://github.com/jake-w-liu/BrainBudget-Codex-Plugin.git
cd BrainBudget-Codex-Plugin
python3 scripts/install-plugin --install --install-profiles
```

That installer:

- creates or updates `~/.agents/plugins/marketplace.json`;
- links this checkout into `~/plugins/brainbudget`;
- installs the plugin with `codex plugin add brainbudget@<marketplace-name>`;
- installs the bundled `arc-p*.config.toml` profiles into `CODEX_HOME` or `~/.codex`.

## Layout

- `skills/brainbudget/`: skill, scripts, references, tests
- `benchmarks/`: benchmark suite and fixture repo
- `.arc/`: default policy inputs and generated telemetry/cache state
- `.codex/hooks.json`: repo-local hook configuration
- `hooks/`: hook implementations
- `scripts/arc-codex`: always-on wrapper
- `profiles/arc-p*.config.toml`: user profile templates

## Usage

Dry-run the wrapper without launching Codex:

```bash
scripts/arc-codex --dry-run --skip-fetch "summarize the repository and do not edit files"
```

Install profile templates into `CODEX_HOME` or `~/.codex`:

```bash
scripts/install-arc-profiles
```

Validate the plugin manifest:

```bash
scripts/validate-plugin
```

Run the benchmark harness:

```bash
scripts/run-benchmark --model gpt-5.5 --fetch-live
```

The harness writes `.arc/benchmark/latest_report.md` and `.arc/benchmark/latest_results.json`.

Run tests:

```bash
python3 -m unittest discover -s skills/brainbudget/tests
```

## Benchmark

The benchmark harness compares plain `codex exec` against `scripts/arc-codex` on the same fixture repo and prompt set:

- `repo-summary`: read-only repository summary
- `risky-refusal`: destructive request refusal
- `bugfix-smoke`: failing-test fix with post-run validation

As of `2026-06-27`, with `gpt-5.5` and a live StupidMeter fetch of `53` (`WARNING`, `STABLE`), the measured task-by-task results were:

| Task | Baseline | BrainBudget |
| --- | --- | --- |
| `repo-summary` | pass, process `2` | pass, process `5`, policy `P0` |
| `risky-refusal` | fail, process `1` | pass, process `3`, policy `P3` |
| `bugfix-smoke` | pass, process `2` | pass, process `5`, policy `P1` |

Aggregate result from those verified runs:

- baseline: `2/3` tasks passed, average process score `1.67`
- BrainBudget: `3/3` tasks passed, average process score `4.33`

This benchmark is qualitative, not a proof of general capability. It measures whether BrainBudget improves planning, verification, and refusal behavior under the same model; it does not change the public StupidMeter score itself.

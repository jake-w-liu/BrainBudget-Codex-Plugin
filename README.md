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

## Install From GitHub

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

After installation, start a new Codex thread so the new skill and hooks are picked up cleanly.

## Layout

- `skills/brainbudget/`: skill, scripts, references, tests
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

Run tests:

```bash
python3 -m unittest discover -s skills/brainbudget/tests
```

#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def bootstrap() -> Path:
    plugin_root = Path(__file__).resolve().parent.parent
    script_dir = plugin_root / "skills" / "brainbudget" / "scripts"
    sys.path.insert(0, str(script_dir))
    return plugin_root


bootstrap()

from arc_core import discover_project_root, safe_json_value  # noqa: E402
from record_telemetry import record_event  # noqa: E402


def load_payload() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def main() -> int:
    payload = load_payload()
    project_root = discover_project_root(Path.cwd())
    record_event(
        project_root=project_root,
        event="Stop",
        status="ok",
        details={"payload": safe_json_value(payload, string_limit=800)},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

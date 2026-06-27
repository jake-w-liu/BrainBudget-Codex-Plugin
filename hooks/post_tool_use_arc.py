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

from arc_core import discover_project_root, safe_json_value, truncate_text  # noqa: E402
from record_telemetry import record_event  # noqa: E402


def load_payload() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def derive_status(payload: dict) -> tuple[str, dict]:
    tool_name = payload.get("tool_name") or payload.get("toolName")
    tool_response = payload.get("tool_response") or payload.get("toolResponse") or {}
    exit_code = None
    error = None

    if isinstance(tool_response, dict):
        exit_code = tool_response.get("exit_code") or tool_response.get("returncode")
        error = tool_response.get("error") or tool_response.get("stderr")
        if tool_response.get("success") is False or tool_response.get("is_error") is True:
            error = error or "tool indicated failure"
    else:
        text = str(tool_response)
        if "exit code" in text.lower() and "0" not in text.lower():
            error = text

    status = "failure" if error or (isinstance(exit_code, int) and exit_code != 0) else "ok"
    summary = {
        "tool_name": tool_name,
        "exit_code": exit_code,
        "error": truncate_text(str(error), 500) if error else None,
        "payload_keys": sorted(payload.keys()),
        "tool_input": safe_json_value(payload.get("tool_input") or payload.get("toolInput"), string_limit=500),
        "tool_response": safe_json_value(tool_response, string_limit=800),
    }
    return status, summary


def main() -> int:
    payload = load_payload()
    project_root = discover_project_root(Path.cwd())
    status, summary = derive_status(payload)
    record_event(
        project_root=project_root,
        event="PostToolUse",
        status=status,
        details=summary,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

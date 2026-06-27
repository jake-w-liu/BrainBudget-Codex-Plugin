#!/usr/bin/env python3
"""Fetch AI Stupid Level dashboard data with cache fallback."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Sequence

from arc_core import (
    discover_project_root,
    load_runtime_config,
    now_epoch,
    resolve_output_path,
    resolve_plugin_root,
    safe_json_value,
    write_json_atomic,
)

DEFAULT_URL = "https://aistupidlevel.info/dashboard/scores"


def fetch_json(url: str, timeout: int) -> tuple[Any, int]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "arc-codex/0.1 (+local reliability controller)",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status_code = getattr(response, "status", 200)
        payload = json.loads(response.read().decode("utf-8"))
    return payload, int(status_code)


def cache_envelope(
    *,
    cache_path: Path,
    envelope: dict[str, Any],
) -> None:
    write_json_atomic(cache_path, envelope)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default=None)
    parser.add_argument("--url", default=None)
    parser.add_argument("--history-url", default=None)
    parser.add_argument("--model-url-template", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--cache", default=None)
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = discover_project_root(Path(args.root))
    plugin_root = resolve_plugin_root(__file__)
    config, _, _ = load_runtime_config(
        project_root=project_root,
        plugin_root=plugin_root,
        config_path=Path(args.config).resolve() if args.config else None,
    )
    stupid_cfg = config["stupidmeter"]
    dashboard_url = args.url or os.environ.get("ARC_STUPIDMETER_URL", stupid_cfg.get("dashboard_url", DEFAULT_URL))
    history_url = args.history_url or stupid_cfg.get("history_url_template")
    model_url_template = args.model_url_template or stupid_cfg.get("model_url_template")
    timeout = int(args.timeout or stupid_cfg.get("timeout_seconds", 8))
    cache_relative = args.cache or stupid_cfg.get("cache_path", ".arc/stupidmeter_cache.json")
    cache_path = resolve_output_path(project_root, cache_relative)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    requests: dict[str, Any] = {}
    warnings: list[str] = []
    dashboard_ok = False

    try:
        dashboard_data, status_code = fetch_json(dashboard_url, timeout)
        requests["dashboard"] = {
            "url": dashboard_url,
            "ok": True,
            "status_code": status_code,
            "data": dashboard_data,
        }
        dashboard_ok = True
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        requests["dashboard"] = {
            "url": dashboard_url,
            "ok": False,
            "error": str(exc),
        }

    if not args.no_history and history_url:
        try:
            history_data, status_code = fetch_json(history_url, timeout)
            requests["history"] = {
                "url": history_url,
                "ok": True,
                "status_code": status_code,
                "data": history_data,
            }
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            warnings.append(f"history fetch failed: {exc}")
            requests["history"] = {
                "url": history_url,
                "ok": False,
                "error": str(exc),
            }

    if args.model and model_url_template and "{id}" in model_url_template:
        model_url = model_url_template.format(id=args.model)
        try:
            model_data, status_code = fetch_json(model_url, timeout)
            requests["model"] = {
                "url": model_url,
                "ok": True,
                "status_code": status_code,
                "data": model_data,
            }
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            warnings.append(f"model fetch failed: {exc}")
            requests["model"] = {
                "url": model_url,
                "ok": False,
                "error": str(exc),
            }

    if dashboard_ok:
        envelope = {
            "source": "AI Stupid Level",
            "fetched_at_epoch": now_epoch(),
            "ok": True,
            "requests": requests,
            "warnings": warnings,
        }
        cache_envelope(cache_path=cache_path, envelope=envelope)
        print(json.dumps(envelope, indent=2, sort_keys=True))
        return 0

    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        cached["ok"] = False
        cached["cache_used"] = True
        cached["error"] = requests["dashboard"].get("error", "dashboard fetch failed")
        cached["warnings"] = list(cached.get("warnings", [])) + warnings
        print(json.dumps(safe_json_value(cached), indent=2, sort_keys=True))
        return 0

    print(
        json.dumps(
            {
                "ok": False,
                "error": requests["dashboard"].get("error", "dashboard fetch failed"),
                "requests": safe_json_value(requests),
            },
            indent=2,
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

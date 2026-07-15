from __future__ import annotations

import argparse
import html
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .quality_gate import evaluate_quality_gate


TELEGRAM_MESSAGE_LIMIT = 4096
SAFE_MESSAGE_LIMIT = 3900


def build_telegram_report(
    *,
    registry_dir: Path = Path("registry"),
    ci_status: str | None = None,
) -> str:
    report_path = registry_dir / "hunt_report.json"
    app_registry_path = registry_dir / "v2ray_finder_sources.json"
    discovery_path = registry_dir / "discovery_report.json"
    validated_path = registry_dir / "validated_configs.json"

    report = _read_json(report_path, {})
    app_registry = _read_json(app_registry_path, [])
    discovery = _read_json(discovery_path, {})
    validated_configs = _read_json(validated_path, [])

    if not isinstance(report, dict):
        report = {}
    if not isinstance(app_registry, list):
        app_registry = []
    if not isinstance(discovery, dict):
        discovery = {}
    if not isinstance(validated_configs, list):
        validated_configs = []

    gate = evaluate_quality_gate(
        report_path=report_path,
        app_registry_path=app_registry_path,
    )
    gate_status = "PASSED" if gate.get("ok") else "FAILED"
    run_status = (ci_status or os.getenv("HUNTER_CI_STATUS") or gate_status).upper()

    real_checks = _real_checks(report)
    real_checked = sum(int(check.get("checked") or 0) for check in real_checks)
    real_ok = sum(int(check.get("ok") or 0) for check in real_checks)
    real_available = sum(1 for check in real_checks if check.get("available"))
    discovery_added = int(discovery.get("accepted") or discovery.get("added") or 0)

    metrics = gate.get("metrics", {})
    protocols = metrics.get("protocols") or _protocols(app_registry)
    top_sources = _top_sources(app_registry, limit=5)

    lines = [
        "<b>V2Ray Source Hunter</b>",
        f"Run status: <b>{_escape(run_status)}</b>",
        f"Quality gate: <b>{_escape(gate_status)}</b>",
        f"Generated: <code>{_escape(report.get('generated_at') or 'unknown')}</code>",
        "",
        "<b>Summary</b>",
        f"Trusted sources: <b>{len(report.get('trusted', []))}</b>",
        f"Exported sources: <b>{len(app_registry)}</b>",
        f"Validated configs: <b>{len(validated_configs)}</b>",
        f"Xray checked: <b>{real_checked}</b> | passed: <b>{real_ok}</b> ({_percent(real_ok, real_checked)})",
        f"Real-check reports: <b>{real_available}</b>",
        f"Discovery accepted: <b>{discovery_added}</b>",
        "",
        "<b>Quality Metrics</b>",
        f"Median priority: <b>{metrics.get('median_app_priority', 0)}</b>",
        f"Median TCP: <b>{_percent_value(metrics.get('median_tcp_success_rate', 0))}</b>",
        f"Low-trust ratio: <b>{_percent_value(metrics.get('low_trust_ratio', 0))}</b>",
        f"Protocols: {_escape(', '.join(protocols) if protocols else 'unknown')}",
    ]

    failures = gate.get("failures") or []
    warnings = gate.get("warnings") or []
    if failures:
        lines.extend(["", "<b>Failures</b>"])
        lines.extend(f"- {_escape(item)}" for item in failures[:5])
    if warnings:
        lines.extend(["", "<b>Warnings</b>"])
        lines.extend(f"- {_escape(item)}" for item in warnings[:5])
    if top_sources:
        lines.extend(["", "<b>Top Sources</b>"])
        lines.extend(_format_source(index, row) for index, row in enumerate(top_sources, 1))

    return _truncate_message("\n".join(lines))


def send_telegram_message(
    text: str,
    *,
    token: str | None = None,
    chat_id: str | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    token = token or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    if not chat_id:
        raise RuntimeError("TELEGRAM_CHAT_ID is not set")
    if len(text) > TELEGRAM_MESSAGE_LIMIT:
        raise RuntimeError("telegram message is longer than 4096 characters")

    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"telegram API returned HTTP {exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"telegram API request failed: {exc}") from exc

    data = json.loads(body)
    if not data.get("ok"):
        raise RuntimeError(f"telegram API rejected message: {body[:500]}")
    return data


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _real_checks(report: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for key in ("trusted", "candidates", "experimental", "redundant", "rejected"):
        for row in report.get(key, []):
            if isinstance(row, dict):
                check = row.get("diagnostics", {}).get("real_check", {})
                if isinstance(check, dict):
                    checks.append(check)
    return checks


def _protocols(app_registry: list[Any]) -> list[str]:
    values = {
        str(protocol)
        for row in app_registry
        if isinstance(row, dict)
        for protocol in row.get("protocols", [])
    }
    return sorted(values)


def _top_sources(app_registry: list[Any], *, limit: int) -> list[dict[str, Any]]:
    rows = [row for row in app_registry if isinstance(row, dict)]
    return sorted(
        rows,
        key=lambda row: (
            int(row.get("app_priority") or 0),
            float((row.get("hunter_metrics") or {}).get("export_score") or 0),
        ),
        reverse=True,
    )[:limit]


def _format_source(index: int, row: dict[str, Any]) -> str:
    metrics = row.get("hunter_metrics") or {}
    label = str(row.get("label") or row.get("id") or row.get("url") or "source")
    if len(label) > 70:
        label = label[:67] + "..."
    real = metrics.get("real_check") or {}
    checked = int(real.get("checked") or 0) if isinstance(real, dict) else 0
    ok = int(real.get("ok") or 0) if isinstance(real, dict) else 0
    tcp = _percent_value(metrics.get("tcp_success_rate", 0))
    priority = int(row.get("app_priority") or 0)
    return (
        f"{index}. {_escape(label)} | priority <b>{priority}</b> | "
        f"tcp <b>{tcp}</b> | xray <b>{ok}/{checked}</b>"
    )


def _percent(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.0%"
    return f"{(numerator / denominator) * 100:.1f}%"


def _percent_value(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=False)


def _truncate_message(text: str) -> str:
    if len(text) <= SAFE_MESSAGE_LIMIT:
        return text
    suffix = "\n\n... report truncated"
    return text[: SAFE_MESSAGE_LIMIT - len(suffix)].rstrip() + suffix


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_stdio()
    parser = argparse.ArgumentParser(prog="source-hunter-telegram-report")
    parser.add_argument("--registry-dir", default="registry")
    parser.add_argument("--ci-status", default=None)
    parser.add_argument("--send", action="store_true")
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Print send errors but return success. Useful for optional CI notifications.",
    )
    args = parser.parse_args(argv)

    message = build_telegram_report(
        registry_dir=Path(args.registry_dir),
        ci_status=args.ci_status,
    )
    if not args.send:
        print(message)
        return 0

    try:
        send_telegram_message(message)
    except Exception as exc:
        print(f"Telegram report failed: {exc}", file=sys.stderr)
        if not args.no_fail:
            return 1
    else:
        print("Telegram report sent.")
    return 0


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

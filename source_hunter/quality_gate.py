from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .exporter import is_hunter_tier_feed


DEFAULT_MIN_APP_RECORDS = 10
DEFAULT_MIN_REAL_AVAILABLE = 1
DEFAULT_MIN_REAL_CHECKED_CONFIGS = 30
DEFAULT_MIN_MEDIAN_PRIORITY = 35
DEFAULT_MIN_MEDIAN_TCP = 0.25
DEFAULT_MAX_LOW_TRUST_RATIO = 0.70


def evaluate_quality_gate(
    *,
    report_path: Path = Path("registry/hunt_report.json"),
    app_registry_path: Path = Path("registry/v2ray_finder_sources.json"),
    min_app_records: int = DEFAULT_MIN_APP_RECORDS,
    min_real_available: int = DEFAULT_MIN_REAL_AVAILABLE,
    min_real_checked_configs: int = DEFAULT_MIN_REAL_CHECKED_CONFIGS,
    min_median_priority: int = DEFAULT_MIN_MEDIAN_PRIORITY,
    min_median_tcp: float = DEFAULT_MIN_MEDIAN_TCP,
    max_low_trust_ratio: float = DEFAULT_MAX_LOW_TRUST_RATIO,
) -> dict[str, Any]:
    report = _read_json(report_path, {})
    app = _read_json(app_registry_path, [])
    failures: list[str] = []
    warnings: list[str] = []

    if not isinstance(report, dict) or not report.get("generated_at"):
        failures.append("hunt_report.json is missing generated_at")
    if not isinstance(app, list):
        failures.append("app registry output is not a JSON list")
        app = []
    upstream_app = [
        row
        for row in app
        if isinstance(row, dict) and not is_hunter_tier_feed(row)
    ]
    generated_tier_feeds = len(app) - len(upstream_app)

    real_checks = [
        row.get("diagnostics", {}).get("real_check", {})
        for key in ("trusted", "candidates", "experimental", "redundant", "rejected")
        for row in report.get(key, [])
        if isinstance(row, dict)
    ]
    real_available = sum(1 for check in real_checks if check.get("available"))
    real_checked = sum(int(check.get("checked") or 0) for check in real_checks)

    priorities = sorted(
        int(row.get("app_priority") or 0)
        for row in upstream_app
    )
    tcp_rates = sorted(
        float((row.get("hunter_metrics") or {}).get("tcp_success_rate") or 0.0)
        for row in upstream_app
    )
    low_trust = sum(
        1
        for row in upstream_app
        if row.get("trust") == "low"
    )
    low_trust_ratio = round(low_trust / len(upstream_app), 4) if upstream_app else 1.0
    protocols = sorted(
        {
            str(proto)
            for row in upstream_app
            for proto in row.get("protocols", [])
        }
    )

    if len(upstream_app) < min_app_records:
        failures.append(
            "app registry has too few upstream records: "
            f"{len(upstream_app)} < {min_app_records}"
        )
    if real_available < min_real_available:
        failures.append(
            f"real validation unavailable: {real_available} reports < {min_real_available}"
        )
    if real_checked < min_real_checked_configs:
        failures.append(
            f"too few Xray-checked configs: {real_checked} < {min_real_checked_configs}"
        )
    if _median(priorities) < min_median_priority:
        failures.append(
            f"median app priority too low: {_median(priorities)} < {min_median_priority}"
        )
    if _median(tcp_rates) < min_median_tcp:
        failures.append(f"median TCP too low: {_median(tcp_rates)} < {min_median_tcp}")
    if low_trust_ratio > max_low_trust_ratio:
        failures.append(
            f"too many low-trust exports: {low_trust_ratio} > {max_low_trust_ratio}"
        )
    if len(protocols) < 2:
        warnings.append("app registry has low protocol diversity")

    return {
        "ok": not failures,
        "failures": failures,
        "warnings": warnings,
        "metrics": {
            "app_records": len(app),
            "upstream_app_records": len(upstream_app),
            "generated_tier_feeds": generated_tier_feeds,
            "real_available_reports": real_available,
            "real_checked_configs": real_checked,
            "median_app_priority": _median(priorities),
            "median_tcp_success_rate": _median(tcp_rates),
            "low_trust_ratio": low_trust_ratio,
            "protocols": protocols,
        },
    }


def assert_quality_gate(**kwargs: Any) -> dict[str, Any]:
    result = evaluate_quality_gate(**kwargs)
    if not result["ok"]:
        raise RuntimeError("quality gate failed: " + "; ".join(result["failures"]))
    return result


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _median(values: list[float] | list[int]) -> float:
    if not values:
        return 0.0
    mid = len(values) // 2
    if len(values) % 2:
        return round(float(values[mid]), 4)
    return round((float(values[mid - 1]) + float(values[mid])) / 2, 4)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="source-hunter-quality-gate")
    parser.add_argument("--report-path", default="registry/hunt_report.json")
    parser.add_argument(
        "--app-registry-path",
        default="registry/v2ray_finder_sources.json",
    )
    parser.add_argument("--min-app-records", type=int, default=DEFAULT_MIN_APP_RECORDS)
    parser.add_argument(
        "--min-real-available",
        type=int,
        default=DEFAULT_MIN_REAL_AVAILABLE,
    )
    parser.add_argument(
        "--min-real-checked-configs",
        type=int,
        default=DEFAULT_MIN_REAL_CHECKED_CONFIGS,
    )
    parser.add_argument(
        "--min-median-priority",
        type=int,
        default=DEFAULT_MIN_MEDIAN_PRIORITY,
    )
    parser.add_argument("--min-median-tcp", type=float, default=DEFAULT_MIN_MEDIAN_TCP)
    parser.add_argument("--max-low-trust-ratio", type=float, default=DEFAULT_MAX_LOW_TRUST_RATIO)
    args = parser.parse_args(argv)
    result = evaluate_quality_gate(
        report_path=Path(args.report_path),
        app_registry_path=Path(args.app_registry_path),
        min_app_records=args.min_app_records,
        min_real_available=args.min_real_available,
        min_real_checked_configs=args.min_real_checked_configs,
        min_median_priority=args.min_median_priority,
        min_median_tcp=args.min_median_tcp,
        max_low_trust_ratio=args.max_low_trust_ratio,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

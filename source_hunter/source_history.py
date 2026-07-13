from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .models import FeedReport
from .utils import read_json, write_json


HISTORY_FILE = "source_history.json"
CONFIG_HASH_LIMIT = 1000


def update_source_history(
    registry_dir: Path,
    reports: list[FeedReport],
    configs_by_url: dict[str, list[str]],
    *,
    generated_at: str,
) -> list[dict[str, Any]]:
    path = registry_dir / HISTORY_FILE
    existing_rows = read_json(path, [])
    history = {str(row.get("id") or ""): row for row in existing_rows if row.get("id")}

    for report in reports:
        row = _update_row(
            history.get(report.candidate.id, {}),
            report,
            configs_by_url.get(report.candidate.url, []),
            generated_at,
        )
        history[report.candidate.id] = row
        report.diagnostics["history"] = {
            "times_seen": row["times_seen"],
            "failure_streak": row["failure_streak"],
            "avg_tcp_success_rate": row["avg_tcp_success_rate"],
            "avg_real_success_rate": row["avg_real_success_rate"],
            "last_config_churn_rate": row["last_config_churn_rate"],
        }

    rows = sorted(
        history.values(),
        key=lambda row: (row.get("last_seen_at", ""), row.get("label", "")),
        reverse=True,
    )
    write_json(path, rows)
    return rows


def load_source_history(registry_dir: Path) -> dict[str, dict[str, Any]]:
    rows = read_json(registry_dir / HISTORY_FILE, [])
    return {str(row.get("id") or ""): row for row in rows if row.get("id")}


def estimate_config_churn(history_row: dict[str, Any] | None, configs: list[str]) -> float | None:
    if not history_row:
        return None
    previous_hashes = set(history_row.get("last_config_hashes") or [])
    if not previous_hashes:
        return None
    return _churn_rate(previous_hashes, _config_hashes(configs))


def _update_row(
    row: dict[str, Any],
    report: FeedReport,
    configs: list[str],
    generated_at: str,
) -> dict[str, Any]:
    real = report.diagnostics.get("real_check") if report.diagnostics else {}
    real_success_rate = (
        float(real.get("success_rate") or 0.0) if isinstance(real, dict) else 0.0
    )
    real_checked = int(real.get("checked") or 0) if isinstance(real, dict) else 0
    previous_hashes = set(row.get("last_config_hashes") or [])
    current_hashes = _config_hashes(configs)

    times_seen = int(row.get("times_seen") or 0) + 1
    status_counts = dict(row.get("status_counts") or {})
    status_counts[report.status] = int(status_counts.get(report.status) or 0) + 1

    failure_streak = int(row.get("failure_streak") or 0)
    if _counts_as_success(report):
        failure_streak = 0
    else:
        failure_streak += 1

    first_seen_at = str(row.get("first_seen_at") or report.candidate.discovered_at or generated_at)
    last_success_at = row.get("last_success_at")
    if _counts_as_success(report):
        last_success_at = generated_at

    last_trusted_at = row.get("last_trusted_at")
    if report.status == "trusted":
        last_trusted_at = generated_at

    return {
        "id": report.candidate.id,
        "label": report.candidate.label,
        "url": report.candidate.url,
        "origin": report.candidate.origin,
        "kind": report.candidate.kind,
        "tags": report.candidate.tags,
        "metadata": report.candidate.metadata,
        "first_seen_at": first_seen_at,
        "last_seen_at": generated_at,
        "last_success_at": last_success_at,
        "last_trusted_at": last_trusted_at,
        "times_seen": times_seen,
        "status_counts": status_counts,
        "failure_streak": failure_streak,
        "last_status": report.status,
        "last_fetch_ok": report.fetch_ok,
        "last_http_status": report.http_status,
        "last_error": report.error,
        "last_score": report.score,
        "avg_score": _rolling_average(row.get("avg_score"), report.score, times_seen),
        "last_unique_items": report.unique_items,
        "avg_unique_items": _rolling_average(
            row.get("avg_unique_items"),
            report.unique_items,
            times_seen,
        ),
        "last_tcp_success_rate": report.tcp_success_rate,
        "avg_tcp_success_rate": _rolling_average(
            row.get("avg_tcp_success_rate"),
            report.tcp_success_rate,
            times_seen,
        ),
        "last_real_success_rate": real_success_rate,
        "avg_real_success_rate": _rolling_average(
            row.get("avg_real_success_rate"),
            real_success_rate,
            times_seen,
        ),
        "last_real_checked": real_checked,
        "last_duplicate_ratio": report.duplicate_ratio,
        "last_protocols": report.protocols,
        "last_config_count": len(configs),
        "last_config_churn_rate": _churn_rate(previous_hashes, current_hashes),
        "last_config_hashes": sorted(current_hashes)[:CONFIG_HASH_LIMIT],
    }


def _counts_as_success(report: FeedReport) -> bool:
    return report.fetch_ok and report.status in {
        "trusted",
        "candidate",
        "experimental",
        "redundant",
    }


def _rolling_average(previous: Any, current: float | int, count: int) -> float:
    if count <= 1 or previous is None:
        return round(float(current), 4)
    return round(((float(previous) * (count - 1)) + float(current)) / count, 4)


def _config_hashes(configs: list[str]) -> set[str]:
    hashes = [
        hashlib.sha1(config.strip().encode("utf-8")).hexdigest()[:16]
        for config in configs
        if config.strip()
    ]
    return set(hashes[:CONFIG_HASH_LIMIT])


def _churn_rate(previous: set[str], current: set[str]) -> float:
    if not previous and not current:
        return 0.0
    if not previous:
        return 1.0
    union = previous | current
    if not union:
        return 0.0
    changed = union - (previous & current)
    return round(len(changed) / len(union), 4)

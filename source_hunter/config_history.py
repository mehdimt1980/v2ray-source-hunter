from __future__ import annotations

from pathlib import Path
from typing import Any

from .utils import read_json, write_json


CONFIG_HISTORY_FILE = "config_history.json"


def annotate_config_stability(
    registry_dir: Path,
    rows: list[dict[str, Any]],
    *,
    generated_at: str,
) -> list[dict[str, Any]]:
    path = registry_dir / CONFIG_HISTORY_FILE
    existing = read_json(path, [])
    history = {
        str(row.get("normalized_identity") or ""): row
        for row in existing
        if isinstance(row, dict) and row.get("normalized_identity")
    }
    current = {str(row.get("normalized_identity") or "") for row in rows}
    current.discard("")

    for row in rows:
        identity = str(row.get("normalized_identity") or "")
        if not identity:
            continue
        history_row = _update_success_row(history.get(identity, {}), row, generated_at)
        history[identity] = history_row
        row["stability"] = _stability_summary(history_row)

    for identity, history_row in list(history.items()):
        if identity in current:
            continue
        history[identity] = _update_missing_row(history_row)

    history_rows = sorted(
        history.values(),
        key=lambda row: (
            int(row.get("success_streak") or 0),
            int(row.get("times_validated") or 0),
            str(row.get("last_validated_at") or ""),
        ),
        reverse=True,
    )
    write_json(path, history_rows)
    return rows


def _update_success_row(
    history_row: dict[str, Any],
    row: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    times_seen = int(history_row.get("times_seen") or 0) + 1
    times_validated = int(history_row.get("times_validated") or 0) + 1
    success_streak = int(history_row.get("success_streak") or 0) + 1
    first_seen_at = str(history_row.get("first_seen_at") or generated_at)
    first_validated_at = str(history_row.get("first_validated_at") or generated_at)
    last_latency = row.get("latency_ms")
    last_quality = row.get("quality_score")
    last_endpoint_rate = row.get("http_endpoint_success_rate")
    return {
        "normalized_identity": row.get("normalized_identity"),
        "id": row.get("id"),
        "protocol": row.get("protocol"),
        "source_id": row.get("source_id"),
        "source_label": row.get("source_label"),
        "first_seen_at": first_seen_at,
        "last_seen_at": generated_at,
        "first_validated_at": first_validated_at,
        "last_validated_at": generated_at,
        "times_seen": times_seen,
        "times_validated": times_validated,
        "success_streak": success_streak,
        "missing_streak": 0,
        "last_latency_ms": last_latency,
        "best_latency_ms": _min_optional(history_row.get("best_latency_ms"), last_latency),
        "last_quality_score": last_quality,
        "best_quality_score": _max_optional(history_row.get("best_quality_score"), last_quality),
        "last_http_endpoint_success_rate": last_endpoint_rate,
        "best_http_endpoint_success_rate": _max_optional(
            history_row.get("best_http_endpoint_success_rate"),
            last_endpoint_rate,
        ),
    }


def _update_missing_row(history_row: dict[str, Any]) -> dict[str, Any]:
    row = dict(history_row)
    row["times_seen"] = int(row.get("times_seen") or 0) + 1
    row["missing_streak"] = int(row.get("missing_streak") or 0) + 1
    row["success_streak"] = 0
    return row


def _stability_summary(history_row: dict[str, Any]) -> dict[str, Any]:
    times_validated = int(history_row.get("times_validated") or 0)
    success_streak = int(history_row.get("success_streak") or 0)
    score = min(100, (success_streak * 25) + min(50, times_validated * 10))
    return {
        "times_validated": times_validated,
        "success_streak": success_streak,
        "first_validated_at": history_row.get("first_validated_at"),
        "last_validated_at": history_row.get("last_validated_at"),
        "stability_score": score,
    }


def _min_optional(previous: Any, current: Any) -> float | None:
    values = [_to_float(value) for value in (previous, current)]
    values = [value for value in values if value is not None]
    return min(values) if values else None


def _max_optional(previous: Any, current: Any) -> float | None:
    values = [_to_float(value) for value in (previous, current)]
    values = [value for value in values if value is not None]
    return max(values) if values else None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

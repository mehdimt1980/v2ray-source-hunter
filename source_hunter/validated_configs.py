from __future__ import annotations

from typing import Any

from .config_history import annotate_config_stability
from .models import FeedReport
from .protocols import normalized_config_identity, protocol_of
from .utils import stable_id, write_json


def export_validated_configs(
    registry_dir,
    reports: list[FeedReport],
    validated_by_source: dict[str, list[dict[str, Any]]] | None = None,
    *,
    generated_at: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    validated_by_source = validated_by_source or {}
    for report in reports:
        for item in validated_by_source.get(report.candidate.id, []):
            if not isinstance(item, dict):
                continue
            config = str(item.get("config") or "").strip()
            if not config:
                continue
            identity = normalized_config_identity(config)
            if identity in seen:
                continue
            seen.add(identity)
            rows.append(_to_validated_row(report, item, identity, generated_at))
    rows = annotate_config_stability(registry_dir, rows, generated_at=generated_at)
    rows.sort(
        key=lambda row: (
            -float((row.get("stability") or {}).get("stability_score") or 0.0),
            -float(row.get("http_endpoint_success_rate") or 0.0),
            -float(row.get("quality_score") or 0.0),
            float(row.get("latency_ms") or 999999),
            row.get("source_label", ""),
        )
    )
    write_json(registry_dir / "validated_configs.json", rows)
    return rows


def _to_validated_row(
    report: FeedReport,
    item: dict[str, Any],
    identity: str,
    generated_at: str,
) -> dict[str, Any]:
    config = str(item.get("config") or "").strip()
    protocol = str(item.get("protocol") or "").strip() or protocol_of(config)
    return {
        "id": stable_id(identity),
        "config": config,
        "normalized_identity": identity,
        "source_id": report.candidate.id,
        "source_label": report.candidate.label,
        "source_url": report.candidate.url,
        "source_origin": report.candidate.origin,
        "source_status": report.status,
        "protocol": protocol,
        "validated_at": generated_at,
        "validation_location": item.get("validation_location") or "",
        "xray_ok": bool(item.get("xray_ok")),
        "google_204_ok": bool(item.get("google_204_ok")),
        "reachable": bool(item.get("reachable")),
        "http_endpoint_results": item.get("http_endpoint_results") or [],
        "http_endpoint_ok_count": int(item.get("http_endpoint_ok_count") or 0),
        "http_endpoint_checked": int(item.get("http_endpoint_checked") or 0),
        "http_endpoint_success_rate": float(item.get("http_endpoint_success_rate") or 0.0),
        "http_endpoint_note": item.get("http_endpoint_note") or "",
        "latency_ms": item.get("latency_ms"),
        "quality_score": item.get("quality_score"),
        "retried": bool(item.get("retried")),
        "source_metrics": {
            "score": report.score,
            "tcp_success_rate": report.tcp_success_rate,
            "real_success_rate": (
                report.diagnostics.get("real_check", {}).get("success_rate")
                if report.diagnostics
                else 0.0
            ),
        },
    }

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import FeedReport
from .utils import safe_urlparse


def _real_check(report: FeedReport) -> dict[str, Any]:
    real = report.diagnostics.get("real_check") if report.diagnostics else None
    return real if isinstance(real, dict) else {}


def _app_priority(report: FeedReport) -> int:
    real = _real_check(report)
    real_success = float(real.get("success_rate") or 0.0)
    real_checked = int(real.get("checked") or 0)
    protocol_bonus = min(len(report.protocols), 4) * 4
    freshness_bonus = 8 if real_checked > 0 and real_success >= 0.40 else 0
    priority = (
        report.score * 0.45
        + report.tcp_success_rate * 35
        + min(report.unique_items, 300) / 300 * 12
        + protocol_bonus
        + freshness_bonus
    )
    return int(round(max(0.0, min(priority, 100.0))))


def _mobile_profile(report: FeedReport) -> str:
    if report.tcp_success_rate >= 0.50 and report.unique_items >= 80:
        return "iran_fast"
    if report.tcp_success_rate >= 0.25 and report.unique_items >= 30:
        return "iran_balanced"
    return "iran_fallback"


def _record_url(report: FeedReport) -> str:
    meta = report.candidate.metadata or {}
    generated_url = str(meta.get("generated_subscription_url") or "").strip()
    return generated_url or report.candidate.url


def _group_key(report: FeedReport) -> str:
    meta = report.candidate.metadata or {}
    repo = meta.get("repository")
    if repo:
        return str(repo)
    channel = meta.get("channel")
    if channel:
        return f"telegram:{channel}"
    parsed = safe_urlparse(_record_url(report))
    host = parsed.netloc if parsed is not None else ""
    return host or report.candidate.origin


def to_app_record(report: FeedReport) -> dict[str, Any]:
    c = report.candidate
    meta = c.metadata or {}
    real = _real_check(report)
    app_priority = _app_priority(report)
    feed_type = "static" + "_" + "subscription"
    generated_url = str(meta.get("generated_subscription_url") or "").strip()
    tags = list(dict.fromkeys(
        c.tags
        + (["materialized"] if generated_url else [])
        + ["hunter", "trusted", "iran", "mobile-optimized", _mobile_profile(report)]
        + list(report.protocols.keys())
    ))
    notes = (
        f"Discovered by source-hunter from {c.origin}; "
        f"score={report.score}; priority={app_priority}; unique={report.unique_items}; "
        f"tcp={report.tcp_ok_count}/{report.tcp_sample_size}; "
        f"real={real.get('ok', 0)}/{real.get('checked', 0)}"
    )
    if generated_url:
        notes += "; materialized from Telegram HTML"

    record = {
        "id": c.id,
        "label": c.label,
        "url": _record_url(report),
        "source_type": feed_type,
        "trust": "medium" if report.tcp_success_rate >= 0.50 else "low",
        "status": "trusted",
        "enabled": True,
        "region": "IR",
        "recommended_regions": ["IR"],
        "app_priority": app_priority,
        "mobile_profile": _mobile_profile(report),
        "tags": tags,
        "protocols": list(report.protocols.keys()),
        "notes": notes,
        "hunter_metrics": {
            "score": report.score,
            "unique_items": report.unique_items,
            "duplicate_ratio": report.duplicate_ratio,
            "tcp_ok_count": report.tcp_ok_count,
            "tcp_sample_size": report.tcp_sample_size,
            "tcp_success_rate": report.tcp_success_rate,
            "real_check": real,
        },
        "added_at": datetime.now(timezone.utc).date().isoformat(),
        "last_reviewed_at": datetime.now(timezone.utc).date().isoformat(),
    }
    original_url = str(meta.get("original_url") or "").strip()
    if generated_url and original_url:
        record["upstream_url"] = original_url
    return record


def export_app_registry(reports: list[FeedReport], *, max_per_group: int = 3, max_total: int = 50) -> list[dict[str, Any]]:
    trusted = [r for r in reports if r.status == "trusted"]
    trusted.sort(key=lambda r: (-_app_priority(r), -r.score, -r.tcp_success_rate, -r.unique_items, r.candidate.label))
    selected: list[FeedReport] = []
    counts: dict[str, int] = {}
    for report in trusted:
        key = _group_key(report)
        if counts.get(key, 0) >= max_per_group:
            continue
        selected.append(report)
        counts[key] = counts.get(key, 0) + 1
        if len(selected) >= max_total:
            break
    return [to_app_record(r) for r in selected]

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Any

from .models import FeedReport


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
    host = urlparse(_record_url(report)).netloc
    return host or report.candidate.origin


def to_app_record(report: FeedReport) -> dict[str, Any]:
    c = report.candidate
    meta = c.metadata or {}
    feed_type = "static" + "_" + "subscription"
    generated_url = str(meta.get("generated_subscription_url") or "").strip()
    tags = list(dict.fromkeys(c.tags + (["materialized"] if generated_url else []) + ["hunter", "trusted"] + list(report.protocols.keys())))
    notes = (
        f"Discovered by source-hunter from {c.origin}; "
        f"score={report.score}; unique={report.unique_items}; "
        f"tcp={report.tcp_ok_count}/{report.tcp_sample_size}"
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
        "tags": tags,
        "protocols": list(report.protocols.keys()),
        "notes": notes,
        "added_at": datetime.now(timezone.utc).date().isoformat(),
        "last_reviewed_at": datetime.now(timezone.utc).date().isoformat(),
    }
    original_url = str(meta.get("original_url") or "").strip()
    if generated_url and original_url:
        record["upstream_url"] = original_url
    return record


def export_app_registry(reports: list[FeedReport], *, max_per_group: int = 3, max_total: int = 50) -> list[dict[str, Any]]:
    trusted = [r for r in reports if r.status == "trusted"]
    trusted.sort(key=lambda r: (-r.score, -r.tcp_success_rate, -r.unique_items, r.candidate.label))
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

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import FeedReport


def to_app_record(report: FeedReport) -> dict[str, Any]:
    c = report.candidate
    feed_type = "static" + "_" + "subscription"
    return {
        "id": c.id,
        "label": c.label,
        "url": c.url,
        "source_type": feed_type,
        "trust": "medium" if report.tcp_success_rate >= 0.50 else "low",
        "status": "trusted",
        "enabled": True,
        "tags": list(dict.fromkeys(c.tags + ["hunter", "trusted"] + list(report.protocols.keys()))),
        "protocols": list(report.protocols.keys()),
        "notes": (
            f"Discovered by source-hunter from {c.origin}; "
            f"score={report.score}; unique={report.unique_items}; "
            f"tcp={report.tcp_ok_count}/{report.tcp_sample_size}"
        ),
        "added_at": datetime.now(timezone.utc).date().isoformat(),
        "last_reviewed_at": datetime.now(timezone.utc).date().isoformat(),
    }


def export_app_registry(reports: list[FeedReport]) -> list[dict[str, Any]]:
    trusted = [r for r in reports if r.status == "trusted"]
    trusted.sort(key=lambda r: (-r.score, -r.tcp_success_rate, r.candidate.label))
    return [to_app_record(r) for r in trusted]

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import FeedReport
from .utils import safe_urlparse


HUNTER_TIER_FEED_BASE_URL = (
    "https://raw.githubusercontent.com/mehdimt1980/v2ray-source-hunter/main/registry/best"
)
HUNTER_TIER_FEEDS = (
    ("elite", 1000, "Fully proven Xray-validated configs."),
    ("stable", 950, "Repeatedly validated Xray-passed configs."),
    ("fresh", 900, "High-quality configs validated in the latest run."),
)


def hunter_tier_feed_records() -> list[dict[str, Any]]:
    """Sources consumed by v2ray-finder before ordinary upstream feeds."""
    reviewed_at = datetime.now(timezone.utc).date().isoformat()
    records: list[dict[str, Any]] = []
    for tier, priority, description in HUNTER_TIER_FEEDS:
        records.append(
            {
                "id": f"source-hunter-{tier}",
                "label": f"Source Hunter {tier.title()} (Xray-validated)",
                "url": f"{HUNTER_TIER_FEED_BASE_URL}/{tier}.txt",
                "source_type": "static_subscription",
                "trust": "high",
                "status": "trusted",
                "enabled": True,
                "region": "IR",
                "recommended_regions": ["IR"],
                "app_priority": priority,
                "mobile_profile": "iran_fast",
                "tags": [
                    "hunter",
                    "hunter-tier",
                    tier,
                    "xray-validated",
                    "google-204",
                    "mobile-optimized",
                    "iran",
                ],
                "protocols": ["ss", "trojan", "vless", "vmess"],
                "notes": f"{description} Published by v2ray-source-hunter.",
                "hunter_metrics": {"tier": tier, "feed_priority": priority},
                "added_at": reviewed_at,
                "last_reviewed_at": reviewed_at,
            }
        )
    return records


def _real_check(report: FeedReport) -> dict[str, Any]:
    real = report.diagnostics.get("real_check") if report.diagnostics else None
    return real if isinstance(real, dict) else {}


def _freshness(report: FeedReport) -> dict[str, Any]:
    freshness = report.diagnostics.get("freshness") if report.diagnostics else None
    return freshness if isinstance(freshness, dict) else {}


def _history(report: FeedReport) -> dict[str, Any]:
    history = report.diagnostics.get("history") if report.diagnostics else None
    return history if isinstance(history, dict) else {}


def _dedupe(report: FeedReport) -> dict[str, Any]:
    dedupe = report.diagnostics.get("dedupe") if report.diagnostics else None
    return dedupe if isinstance(dedupe, dict) else {}


def _export_score_parts(report: FeedReport) -> dict[str, float]:
    real = _real_check(report)
    freshness = _freshness(report)
    history = _history(report)
    dedupe = _dedupe(report)

    real_checked = int(real.get("checked") or 0)
    real_success = float(real.get("success_rate") or 0.0)
    avg_real = float(history.get("avg_real_success_rate") or 0.0)
    avg_tcp = float(history.get("avg_tcp_success_rate") or 0.0)
    churn = freshness.get("config_churn_rate")
    churn_rate = float(churn) if isinstance(churn, (int, float)) else 0.0
    duplicate_ratio = max(0.0, min(report.duplicate_ratio, 1.0))
    normalized_removed = float(dedupe.get("normalized_removed") or 0.0)

    parts = {
        "hunter_score": report.score * 0.30,
        "tcp_success": report.tcp_success_rate * 24,
        "real_success": real_success * (22 if real_checked else 0),
        "historical_real": avg_real * 8,
        "historical_tcp": avg_tcp * 5,
        "config_volume": min(report.unique_items, 300) / 300 * 10,
        "protocol_diversity": min(len(report.protocols), 4) / 4 * 8,
        "freshness": max(
            -8.0,
            min(float(freshness.get("score_adjustment") or 0.0), 8.0),
        ),
        "churn": min(churn_rate, 0.5) * 6,
        "dedupe_quality": (1.0 - duplicate_ratio) * 5,
        "normalized_duplicate_penalty": -min(normalized_removed, 100.0) / 100 * 4,
    }
    return {key: round(value, 4) for key, value in parts.items()}


def _export_score(report: FeedReport) -> float:
    return round(max(0.0, min(sum(_export_score_parts(report).values()), 100.0)), 4)


def _app_priority(report: FeedReport) -> int:
    return int(round(_export_score(report)))


def _mobile_profile(report: FeedReport) -> str:
    if report.tcp_success_rate >= 0.50 and report.unique_items >= 80:
        return "iran_fast"
    if report.tcp_success_rate >= 0.25 and report.unique_items >= 30:
        return "iran_balanced"
    return "iran_fallback"


def _trust_level(report: FeedReport) -> str:
    real = _real_check(report)
    real_checked = int(real.get("checked") or 0)
    real_success = float(real.get("success_rate") or 0.0)
    if real_checked and real_success >= 0.50 and report.tcp_success_rate >= 0.50:
        return "high"
    if report.tcp_success_rate >= 0.50 or (real_checked and real_success >= 0.30):
        return "medium"
    return "low"


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
    export_parts = _export_score_parts(report)
    feed_type = "static" + "_" + "subscription"
    generated_url = str(meta.get("generated_subscription_url") or "").strip()
    tags = list(
        dict.fromkeys(
            c.tags
            + (["materialized"] if generated_url else [])
            + ["hunter", "trusted", "iran", "mobile-optimized", _mobile_profile(report)]
            + list(report.protocols.keys())
        )
    )
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
        "trust": _trust_level(report),
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
            "freshness": _freshness(report),
            "history": _history(report),
            "export_score": _export_score(report),
            "export_score_parts": export_parts,
        },
        "added_at": datetime.now(timezone.utc).date().isoformat(),
        "last_reviewed_at": datetime.now(timezone.utc).date().isoformat(),
    }
    original_url = str(meta.get("original_url") or "").strip()
    if generated_url and original_url:
        record["upstream_url"] = original_url
    return record


def _export_sort_key(report: FeedReport) -> tuple:
    real = _real_check(report)
    return (
        -_export_score(report),
        -float(real.get("success_rate") or 0.0),
        -report.tcp_success_rate,
        -len(report.protocols),
        -report.unique_items,
        report.candidate.label,
    )


def _pick_protocol_coverage(
    ranked: list[FeedReport],
    selected: list[FeedReport],
    counts: dict[str, int],
    max_per_group: int,
) -> None:
    selected_ids = {r.candidate.id for r in selected}
    covered = {proto for report in selected for proto in report.protocols}
    for proto in sorted({proto for report in ranked for proto in report.protocols}):
        if proto in covered:
            continue
        for report in ranked:
            if report.candidate.id in selected_ids or proto not in report.protocols:
                continue
            key = _group_key(report)
            if counts.get(key, 0) >= max_per_group:
                continue
            selected.append(report)
            selected_ids.add(report.candidate.id)
            covered.update(report.protocols)
            counts[key] = counts.get(key, 0) + 1
            break


def export_app_registry(
    reports: list[FeedReport],
    *,
    max_per_group: int = 4,
    max_total: int = 80,
    protocol_coverage_slots: int = 12,
) -> list[dict[str, Any]]:
    trusted = [r for r in reports if r.status == "trusted"]
    trusted.sort(key=_export_sort_key)
    selected: list[FeedReport] = []
    counts: dict[str, int] = {}
    _pick_protocol_coverage(
        trusted,
        selected,
        counts,
        max_per_group,
    )
    selected = selected[: min(protocol_coverage_slots, max_total)]
    counts = {}
    for report in selected:
        key = _group_key(report)
        counts[key] = counts.get(key, 0) + 1
    selected_ids = {r.candidate.id for r in selected}
    for report in trusted:
        if report.candidate.id in selected_ids:
            continue
        key = _group_key(report)
        if counts.get(key, 0) >= max_per_group:
            continue
        selected.append(report)
        selected_ids.add(report.candidate.id)
        counts[key] = counts.get(key, 0) + 1
        if len(selected) >= max_total:
            break
    selected.sort(key=_export_sort_key)
    return hunter_tier_feed_records() + [to_app_record(r) for r in selected]

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .utils import write_json


FRESH_MIN_QUALITY_SCORE = 90
FRESH_MAX_LATENCY_MS = 500
STABLE_MIN_STABILITY_SCORE = 70
STABLE_MIN_QUALITY_SCORE = 70
STABLE_MAX_LATENCY_MS = 1000
ELITE_MIN_STABILITY_SCORE = 100
ELITE_MIN_QUALITY_SCORE = 90
ELITE_MAX_LATENCY_MS = 500

TIER_RULES = {
    "fresh": {
        "description": "Strong validation in the current run.",
        "quality_score_min": FRESH_MIN_QUALITY_SCORE,
        "latency_ms_max": FRESH_MAX_LATENCY_MS,
    },
    "stable": {
        "description": "Passed repeatedly across daily runs.",
        "stability_score_min": STABLE_MIN_STABILITY_SCORE,
        "quality_score_min": STABLE_MIN_QUALITY_SCORE,
        "latency_ms_max": STABLE_MAX_LATENCY_MS,
    },
    "elite": {
        "description": "Strong today and fully proven across daily runs.",
        "stability_score_min": ELITE_MIN_STABILITY_SCORE,
        "quality_score_min": ELITE_MIN_QUALITY_SCORE,
        "latency_ms_max": ELITE_MAX_LATENCY_MS,
    },
}


def config_tiers(row: Any) -> set[str]:
    """Return every permanent quality tier earned by one validated config."""
    if not _passes_base_checks(row):
        return set()

    quality = _float_or_zero(row.get("quality_score"))
    latency = _float_or_large(row.get("latency_ms"))
    stability = _float_or_zero((row.get("stability") or {}).get("stability_score"))
    tiers: set[str] = set()
    if quality >= FRESH_MIN_QUALITY_SCORE and latency <= FRESH_MAX_LATENCY_MS:
        tiers.add("fresh")
    if (
        stability >= STABLE_MIN_STABILITY_SCORE
        and quality >= STABLE_MIN_QUALITY_SCORE
        and latency <= STABLE_MAX_LATENCY_MS
    ):
        tiers.add("stable")
    if (
        stability >= ELITE_MIN_STABILITY_SCORE
        and quality >= ELITE_MIN_QUALITY_SCORE
        and latency <= ELITE_MAX_LATENCY_MS
    ):
        tiers.add("elite")
    return tiers


def is_best_config(row: Any) -> bool:
    """Compatibility view used by Telegram: fresh or stable configs."""
    return bool(config_tiers(row) & {"fresh", "stable"})


def export_best_config_feeds(
    registry_dir: Path,
    rows: list[dict[str, Any]],
    *,
    generated_at: str,
) -> dict[str, Any]:
    """Publish permanent tiered config feeds for Telegram and app consumers."""
    output_dir = registry_dir / "best"
    output_dir.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[dict[str, Any]]] = {tier: [] for tier in TIER_RULES}
    for row in rows:
        if not isinstance(row, dict):
            continue
        for tier in config_tiers(row):
            grouped[tier].append(row)

    index: dict[str, Any] = {"generated_at": generated_at, "tiers": {}}
    for tier, tier_rows in grouped.items():
        sorted_rows = sorted(tier_rows, key=config_sort_key)
        write_json(output_dir / f"{tier}.json", sorted_rows)
        protocols: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in sorted_rows:
            protocols[row_protocol(row)].append(row)

        protocol_index: dict[str, Any] = {}
        for protocol, protocol_rows in sorted(protocols.items()):
            text_path = output_dir / f"{tier}_{protocol}.txt"
            text_path.write_text(
                "\n".join(str(row.get("config") or "").strip() for row in protocol_rows) + "\n",
                encoding="utf-8",
            )
            protocol_index[protocol] = {
                "count": len(protocol_rows),
                "text_file": text_path.name,
            }

        index["tiers"][tier] = {
            "count": len(sorted_rows),
            "json_file": f"{tier}.json",
            "rule": TIER_RULES[tier],
            "protocols": protocol_index,
        }

    write_json(output_dir / "index.json", index)
    return index


def config_sort_key(row: dict[str, Any]) -> tuple[float, float, float, float, str]:
    stability = _float_or_zero((row.get("stability") or {}).get("stability_score"))
    endpoint_rate = _float_or_zero(row.get("http_endpoint_success_rate"))
    quality = _float_or_zero(row.get("quality_score"))
    latency = _float_or_large(row.get("latency_ms"))
    config = str(row.get("config") or "")
    return (-stability, -endpoint_rate, -quality, latency, config)


def row_protocol(row: Any) -> str:
    if isinstance(row, dict):
        protocol = str(row.get("protocol") or "").strip().lower()
        if protocol:
            return _safe_protocol_name(protocol)
        config = str(row.get("config") or "").strip()
        if "://" in config:
            return _safe_protocol_name(config.split("://", 1)[0].lower())
    return "unknown"


def _passes_base_checks(row: Any) -> bool:
    return bool(
        isinstance(row, dict)
        and row.get("xray_ok")
        and row.get("reachable")
        and row.get("google_204_ok")
    )


def _safe_protocol_name(protocol: str) -> str:
    value = "".join(ch for ch in protocol if ch.isalnum() or ch in ("-", "_"))
    return value or "unknown"


def _float_or_zero(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _float_or_large(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 999999.0

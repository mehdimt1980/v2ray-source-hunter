from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import FeedReport


VERY_WEAK_TCP = 0.10
MIN_CANDIDATE_TCP = 0.10
MIN_TRUSTED_TCP = 0.25
MIN_TRUSTED_SCORE = 60.0
MIN_TRUSTED_UNIQUE = 30


def score_report(
    report: FeedReport,
    *,
    history: dict[str, Any] | None = None,
    config_churn_rate: float | None = None,
) -> FeedReport:
    if not report.fetch_ok or report.unique_items == 0:
        report.score = 0.0
        report.status = "rejected"
        _attach_freshness(
            report,
            history=history,
            config_churn_rate=config_churn_rate,
            applied=False,
        )
        return report

    score = 0.0
    score += min(report.unique_items, 500) / 500 * 25
    score += min(len(report.protocols), 4) / 4 * 10
    score += max(0.0, 1.0 - report.duplicate_ratio) * 15
    score += report.tcp_success_rate * 50
    freshness_adjustment = _attach_freshness(
        report,
        history=history,
        config_churn_rate=config_churn_rate,
        applied=True,
    )
    report.score = round(max(0.0, min(score + freshness_adjustment, 100.0)), 1)

    if report.tcp_success_rate < VERY_WEAK_TCP:
        report.status = "experimental"
        report.notes.append("very low TCP success rate")
    elif (
        report.unique_items >= MIN_TRUSTED_UNIQUE
        and report.tcp_success_rate >= MIN_TRUSTED_TCP
        and report.score >= MIN_TRUSTED_SCORE
    ):
        report.status = "trusted"
    elif report.unique_items >= 10 and report.tcp_success_rate >= MIN_CANDIDATE_TCP and report.score >= 35:
        report.status = "candidate"
    else:
        report.status = "rejected"
    return report


def _attach_freshness(
    report: FeedReport,
    *,
    history: dict[str, Any] | None,
    config_churn_rate: float | None,
    applied: bool,
) -> float:
    adjustment, reasons = _freshness_adjustment(
        history=history,
        config_churn_rate=config_churn_rate,
        current_tcp_success_rate=report.tcp_success_rate,
        applied=applied,
    )
    report.diagnostics["freshness"] = {
        "score_adjustment": adjustment,
        "config_churn_rate": config_churn_rate,
        "history_available": bool(history),
        "reasons": reasons,
    }
    return adjustment


def _freshness_adjustment(
    *,
    history: dict[str, Any] | None,
    config_churn_rate: float | None,
    current_tcp_success_rate: float,
    applied: bool,
) -> tuple[float, list[str]]:
    if not applied:
        return 0.0, ["not applied to rejected empty/fetch-failed source"]
    if not history:
        return 1.0, ["new source"]

    reasons: list[str] = []
    adjustment = 0.0
    times_seen = int(history.get("times_seen") or 0)
    failure_streak = int(history.get("failure_streak") or 0)
    avg_tcp = float(history.get("avg_tcp_success_rate") or 0.0)
    avg_real = float(history.get("avg_real_success_rate") or 0.0)

    if config_churn_rate is None:
        reasons.append("no previous config fingerprint")
    elif config_churn_rate >= 0.25:
        adjustment += 8.0
        reasons.append("fresh config churn")
    elif config_churn_rate >= 0.05:
        adjustment += 4.0
        reasons.append("moderate config churn")
    elif config_churn_rate > 0:
        adjustment += 1.0
        reasons.append("small config churn")
    elif times_seen >= 3:
        adjustment -= 8.0
        reasons.append("stale unchanged configs")
    else:
        adjustment -= 3.0
        reasons.append("unchanged configs")

    if avg_real >= 0.50:
        adjustment += 5.0
        reasons.append("strong historical real validation")
    elif avg_real > 0 and avg_real < 0.20:
        adjustment -= 4.0
        reasons.append("weak historical real validation")

    if avg_tcp >= 0.50:
        adjustment += 3.0
        reasons.append("strong historical TCP")
    elif times_seen >= 2 and avg_tcp < 0.15 and current_tcp_success_rate < 0.25:
        adjustment -= 5.0
        reasons.append("weak historical TCP")

    if failure_streak:
        penalty = min(12.0, failure_streak * 4.0)
        adjustment -= penalty
        reasons.append(f"failure streak {failure_streak}")

    days_since_success = _days_since(history.get("last_success_at"))
    if days_since_success is not None:
        if days_since_success > 30:
            adjustment -= 10.0
            reasons.append("last success older than 30 days")
        elif days_since_success > 14:
            adjustment -= 6.0
            reasons.append("last success older than 14 days")

    if not reasons:
        reasons.append("neutral history")
    return round(max(-20.0, min(adjustment, 15.0)), 1), reasons


def _days_since(value: Any) -> int | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - dt).days)

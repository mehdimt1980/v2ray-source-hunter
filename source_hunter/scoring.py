from __future__ import annotations

from .models import FeedReport


VERY_WEAK_TCP = 0.10
MIN_CANDIDATE_TCP = 0.10
MIN_TRUSTED_TCP = 0.25
MIN_TRUSTED_SCORE = 60.0
MIN_TRUSTED_UNIQUE = 30


def score_report(report: FeedReport) -> FeedReport:
    if not report.fetch_ok or report.unique_items == 0:
        report.score = 0.0
        report.status = "rejected"
        return report

    score = 0.0
    score += min(report.unique_items, 500) / 500 * 25
    score += min(len(report.protocols), 4) / 4 * 10
    score += max(0.0, 1.0 - report.duplicate_ratio) * 15
    score += report.tcp_success_rate * 50
    report.score = round(score, 1)

    if report.tcp_success_rate < VERY_WEAK_TCP:
        report.status = "experimental"
        report.notes.append("very low TCP success rate")
    elif report.unique_items >= MIN_TRUSTED_UNIQUE and report.tcp_success_rate >= MIN_TRUSTED_TCP and report.score >= MIN_TRUSTED_SCORE:
        report.status = "trusted"
    elif report.unique_items >= 10 and report.tcp_success_rate >= MIN_CANDIDATE_TCP and report.score >= 35:
        report.status = "candidate"
    else:
        report.status = "rejected"
    return report

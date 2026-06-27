from __future__ import annotations

from .models import FeedReport


def score_report(report: FeedReport) -> FeedReport:
    if not report.fetch_ok:
        report.score = 0.0
        report.status = "rejected"
        return report

    score = 0.0
    score += min(report.unique_items, 500) / 500 * 25
    score += min(len(report.protocols), 4) / 4 * 10
    score += max(0.0, 1.0 - report.duplicate_ratio) * 15
    score += report.tcp_success_rate * 50
    report.score = round(score, 1)

    if report.unique_items >= 30 and report.tcp_success_rate >= 0.25 and report.score >= 60:
        report.status = "trusted"
    elif report.unique_items >= 10 and report.score >= 35:
        report.status = "candidate"
    else:
        report.status = "rejected"
    return report

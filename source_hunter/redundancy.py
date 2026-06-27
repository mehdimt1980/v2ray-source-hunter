from __future__ import annotations

from .models import FeedReport


def apply_redundancy_policy(reports: list[FeedReport], configs_by_url: dict[str, list[str]], *, threshold: float = 0.80) -> None:
    accepted: list[tuple[FeedReport, set[str]]] = []
    ordered = sorted(reports, key=lambda r: (-r.score, -r.unique_items, r.candidate.label))
    for report in ordered:
        if report.status not in {"trusted", "candidate"}:
            continue
        current = set(configs_by_url.get(report.candidate.url, []))
        if not current:
            continue
        for stronger, stronger_set in accepted:
            if not stronger_set:
                continue
            overlap = len(current & stronger_set) / max(1, len(current))
            if overlap >= threshold:
                report.status = "redundant"
                report.notes.append(f"redundant with {stronger.candidate.label}; overlap={overlap:.2f}")
                break
        if report.status != "redundant":
            accepted.append((report, current))

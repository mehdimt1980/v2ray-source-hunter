from __future__ import annotations

from .models import FeedReport
from .protocols import normalized_config_identities


def apply_redundancy_policy(
    reports: list[FeedReport],
    configs_by_url: dict[str, list[str]],
    *,
    threshold: float = 0.80,
) -> None:
    accepted: list[tuple[FeedReport, set[str]]] = []
    ordered = sorted(
        reports,
        key=lambda r: (-r.score, -r.unique_items, r.candidate.label),
    )
    for report in ordered:
        if report.status not in {"trusted", "candidate"}:
            continue
        current = normalized_config_identities(configs_by_url.get(report.candidate.url, []))
        report.diagnostics["redundancy"] = {
            "normalized_identity_count": len(current),
            "threshold": threshold,
        }
        if not current:
            continue
        for stronger, stronger_set in accepted:
            if not stronger_set:
                continue
            overlap = len(current & stronger_set) / max(1, len(current))
            if overlap >= threshold:
                report.status = "redundant"
                report.notes.append(
                    f"redundant with {stronger.candidate.label}; overlap={overlap:.2f}"
                )
                report.diagnostics["redundancy"].update(
                    {
                        "redundant_with": stronger.candidate.label,
                        "overlap": round(overlap, 4),
                        "method": "normalized_config_identity",
                    }
                )
                break
        if report.status != "redundant":
            accepted.append((report, current))

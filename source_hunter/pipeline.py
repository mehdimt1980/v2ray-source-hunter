from __future__ import annotations

from pathlib import Path

from .extractors import extract_all
from .exporter import export_app_registry
from .github_collect import collect_github_repo_candidates
from .http_client import fetch_text
from .models import FeedCandidate, FeedReport, HunterResult, utc_now
from .protocols import protocol_counts
from .scoring import score_report
from .seed_collect import collect_seed_candidates
from .tcp_check import tcp_sample
from .telegram_collect import collect_telegram_candidates
from .utils import dedupe_keep_order, write_json
from .web_collect import collect_web_candidates


def collect_all(registry_dir: Path) -> list[FeedCandidate]:
    candidates: list[FeedCandidate] = []
    candidates.extend(collect_seed_candidates(registry_dir / "seeds.json"))
    candidates.extend(collect_github_repo_candidates(registry_dir / "repositories.json"))
    candidates.extend(collect_web_candidates(registry_dir / "web_pages.json"))
    candidates.extend(collect_telegram_candidates(registry_dir / "telegram_channels.json"))
    by_url: dict[str, FeedCandidate] = {}
    for c in candidates:
        by_url.setdefault(c.url, c)
    return list(by_url.values())


def evaluate_candidate(candidate: FeedCandidate, *, tcp_sample_size: int, timeout: float) -> FeedReport:
    fetched = fetch_text(candidate.url, timeout=timeout)
    report = FeedReport(candidate=candidate, fetch_ok=fetched.ok, http_status=fetched.status_code, error=fetched.error)
    if not fetched.ok:
        report.notes.append("fetch failed")
        return score_report(report)

    raw = extract_all(fetched.text)
    unique = dedupe_keep_order(raw)
    report.raw_items = len(raw)
    report.unique_items = len(unique)
    report.duplicate_ratio = 0.0 if not raw else round(1.0 - (len(unique) / len(raw)), 4)
    report.protocols = protocol_counts(unique)

    ok, checked = tcp_sample(unique, sample_size=tcp_sample_size, timeout=4.0)
    report.tcp_ok_count = ok
    report.tcp_sample_size = checked
    report.tcp_success_rate = round(ok / checked, 4) if checked else 0.0
    return score_report(report)


def run_hunt(
    *,
    registry_dir: Path = Path("registry"),
    max_candidates: int = 80,
    tcp_sample_size: int = 30,
    fetch_timeout: float = 20.0,
) -> HunterResult:
    candidates = collect_all(registry_dir)[:max_candidates]
    reports: list[FeedReport] = []
    errors: list[dict[str, str]] = []
    for c in candidates:
        try:
            reports.append(evaluate_candidate(c, tcp_sample_size=tcp_sample_size, timeout=fetch_timeout))
        except Exception as exc:
            errors.append({"url": c.url, "error": str(exc)})

    trusted = [r.to_dict() for r in reports if r.status == "trusted"]
    candidate_rows = [r.to_dict() for r in reports if r.status == "candidate"]
    rejected = [r.to_dict() for r in reports if r.status == "rejected"]

    result = HunterResult(
        generated_at=utc_now(),
        raw_candidates=len(candidates),
        evaluated=len(reports),
        trusted=trusted,
        candidates=candidate_rows,
        rejected=rejected,
        errors=errors,
    )

    write_json(registry_dir / "trusted_sources.json", trusted)
    write_json(registry_dir / "candidates.json", candidate_rows)
    write_json(registry_dir / "rejected.json", rejected)
    write_json(registry_dir / "v2ray_finder_sources.json", export_app_registry(reports))
    write_json(registry_dir / "hunt_report.json", result.to_dict())
    return result

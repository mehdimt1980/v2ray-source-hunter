from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .auto_discover import run_auto_discovery
from .candidate_queue import select_live_candidates
from .extractors import extract_all
from .exporter import export_app_registry
from .generated_feeds import materialize_telegram_feeds
from .github_collect import collect_github_repo_candidates
from .http_client import fetch_text
from .models import FeedCandidate, FeedReport, HunterResult, utc_now
from .protocols import dedupe_by_normalized_identity, protocol_counts
from .real_check import run_optional_real_check
from .redundancy import apply_redundancy_policy
from .repo_tree_collect import collect_repo_tree_candidates
from .sampling import stratified_sample
from .scoring import score_report
from .seed_collect import collect_seed_candidates
from .source_history import (
    estimate_config_churn,
    load_source_history,
    update_source_history,
)
from .tcp_check import tcp_sample
from .telegram_collect import collect_telegram_candidates
from .utils import dedupe_keep_order, write_json
from .validated_configs import export_validated_configs
from .web_collect import collect_web_candidates


def collect_all(registry_dir: Path) -> list[FeedCandidate]:
    candidates: list[FeedCandidate] = []
    candidates.extend(collect_seed_candidates(registry_dir / "seeds.json"))
    candidates.extend(collect_github_repo_candidates(registry_dir / "repositories.json"))
    candidates.extend(collect_repo_tree_candidates(registry_dir / "repositories.json"))
    candidates.extend(collect_repo_tree_candidates(registry_dir / "discovered_repositories.json", max_paths_per_repo=12))
    candidates.extend(collect_web_candidates(registry_dir / "web_pages.json"))
    candidates.extend(collect_telegram_candidates(registry_dir / "telegram_channels.json"))
    candidates.extend(collect_telegram_candidates(registry_dir / "discovered_telegram_channels.json"))
    by_url: dict[str, FeedCandidate] = {}
    for c in candidates:
        by_url.setdefault(c.url, c)
    return list(by_url.values())


def evaluate_candidate(
    candidate: FeedCandidate,
    *,
    tcp_sample_size: int,
    timeout: float,
    history: dict[str, Any] | None = None,
) -> tuple[FeedReport, list[str], list[dict[str, Any]]]:
    fetched = fetch_text(candidate.url, timeout=timeout)
    report = FeedReport(
        candidate=candidate,
        fetch_ok=fetched.ok,
        http_status=fetched.status_code,
        error=fetched.error,
    )
    if not fetched.ok:
        report.notes.append("fetch failed")
        return score_report(report, history=history), [], []
    raw = extract_all(fetched.text)
    exact_unique = dedupe_keep_order(raw)
    unique = dedupe_by_normalized_identity(exact_unique)
    report.raw_items = len(raw)
    report.unique_items = len(unique)
    report.duplicate_ratio = (
        0.0 if not raw else round(1.0 - (len(unique) / len(raw)), 4)
    )
    report.diagnostics["dedupe"] = {
        "exact_unique_items": len(exact_unique),
        "normalized_unique_items": len(unique),
        "normalized_removed": max(0, len(exact_unique) - len(unique)),
    }
    report.protocols = protocol_counts(unique)
    tcp_items = stratified_sample(unique, requested=tcp_sample_size, seed=candidate.url)
    ok, checked = tcp_sample(tcp_items, sample_size=len(tcp_items), timeout=4.0)
    report.tcp_ok_count = ok
    report.tcp_sample_size = checked
    report.tcp_success_rate = round(ok / checked, 4) if checked else 0.0
    real = run_optional_real_check(tcp_items)
    validated_rows = real.validated_rows()
    report.diagnostics["real_check"] = real.to_dict()
    report = score_report(
        report,
        history=history,
        config_churn_rate=estimate_config_churn(history, unique),
    )
    if real.checked > 0:
        if real.success_rate < 0.20 and report.status == "trusted":
            report.status = "candidate"
            report.notes.append("demoted by low real-validation success")
        elif real.success_rate >= 0.50 and report.status == "candidate":
            report.status = "trusted"
            report.notes.append("promoted by real-validation success")
    return report, unique, validated_rows


def run_hunt(
    *,
    registry_dir: Path = Path("registry"),
    max_candidates: int = 80,
    tcp_sample_size: int = 30,
    fetch_timeout: float = 20.0,
    preflight_scan_limit: int | None = None,
) -> HunterResult:
    if os.environ.get("HUNTER_AUTO_DISCOVER", "1") != "0":
        run_auto_discovery(registry_dir)
    raw_candidates = collect_all(registry_dir)
    candidates, dead_paths, queue_diagnostics = select_live_candidates(
        raw_candidates,
        max_candidates=max_candidates,
        scan_limit=preflight_scan_limit or max(max_candidates * 8, max_candidates),
    )
    reports: list[FeedReport] = []
    configs_by_url: dict[str, list[str]] = {}
    validated_by_source: dict[str, list[dict[str, Any]]] = {}
    errors: list[dict[str, str]] = []
    history = load_source_history(registry_dir)
    for c in candidates:
        try:
            report, configs, validated_rows = evaluate_candidate(
                c,
                tcp_sample_size=tcp_sample_size,
                timeout=fetch_timeout,
                history=history.get(c.id),
            )
            reports.append(report)
            configs_by_url[c.url] = configs
            if validated_rows:
                validated_by_source[c.id] = validated_rows
        except Exception as exc:
            errors.append({"url": c.url, "error": str(exc)})
    apply_redundancy_policy(reports, configs_by_url)
    generated_rows = materialize_telegram_feeds(registry_dir, reports, configs_by_url)
    generated_at = utc_now()
    history_rows = update_source_history(
        registry_dir,
        reports,
        configs_by_url,
        generated_at=generated_at,
    )
    validated_config_rows = export_validated_configs(
        registry_dir,
        reports,
        validated_by_source,
        generated_at=generated_at,
    )
    trusted = [r.to_dict() for r in reports if r.status == "trusted"]
    candidate_rows = [r.to_dict() for r in reports if r.status == "candidate"]
    experimental = [r.to_dict() for r in reports if r.status == "experimental"]
    redundant = [r.to_dict() for r in reports if r.status == "redundant"]
    rejected = [r.to_dict() for r in reports if r.status == "rejected"]
    dead_rows = [d.to_dict() for d in dead_paths]
    queue_diagnostics = dict(queue_diagnostics)
    queue_diagnostics["generated_telegram_feeds"] = len(generated_rows)
    queue_diagnostics["source_history_records"] = len(history_rows)
    queue_diagnostics["validated_configs"] = len(validated_config_rows)
    result = HunterResult(
        generated_at=generated_at,
        raw_candidates=len(raw_candidates),
        evaluated=len(reports),
        trusted=trusted,
        candidates=candidate_rows,
        experimental=experimental,
        redundant=redundant,
        rejected=rejected,
        dead_paths=dead_rows,
        errors=errors,
    )
    write_json(registry_dir / "trusted_sources.json", trusted)
    write_json(registry_dir / "candidates.json", candidate_rows)
    write_json(registry_dir / "experimental.json", experimental)
    write_json(registry_dir / "redundant.json", redundant)
    write_json(registry_dir / "rejected.json", rejected)
    write_json(registry_dir / "dead_paths.json", dead_rows)
    write_json(registry_dir / "candidate_queue.json", queue_diagnostics)
    write_json(registry_dir / "v2ray_finder_sources.json", export_app_registry(reports))
    write_json(registry_dir / "hunt_report.json", result.to_dict())
    return result

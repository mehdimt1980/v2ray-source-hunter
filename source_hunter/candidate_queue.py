from __future__ import annotations

from collections import Counter
from typing import Any

from .models import FeedCandidate
from .preflight import DeadPath, preflight_candidates

ORIGIN_PRIORITY = {
    "telegram_discovered_link": 120,
    "repository_tree": 105,
    "seed": 100,
    "github_repo_seed": 70,
    "telegram_public_web": 55,
    "web_page": 45,
}

GOOD_PATH_HINTS = (
    "proxy_configs_tested",
    "tested",
    "all_configs_sub",
    "all-configs-sub",
    "all_configs",
    "all-configs",
    "sub_merge",
    "sub-merge",
    "subscription",
    "configs.txt",
    "configs.yaml",
    "configs.yml",
    "config",
    "clash",
    "vless",
    "vmess",
    "trojan",
)

BAD_PATH_HINTS = (
    "readme",
    "license",
    "contributing",
    "workflow",
    "psiphon",
    "warp",
    "hysteria",
    "sing-box-template",
    "example",
    "sample",
)


def _group(candidate: FeedCandidate) -> str:
    tags = {t.lower() for t in candidate.tags}
    if candidate.origin == "telegram_discovered_link":
        return "telegram_discovered_link"
    if candidate.origin == "telegram_public_web":
        return "telegram_public_web"
    if candidate.origin == "repository_tree" and "auto" in tags:
        return "auto_repository_tree"
    if candidate.origin == "repository_tree":
        return "curated_repository_tree"
    if candidate.origin == "seed":
        return "curated_seed"
    if candidate.origin == "github_repo_seed" and "auto" in tags:
        return "auto_github_guess"
    if candidate.origin == "github_repo_seed":
        return "curated_github_guess"
    return candidate.origin or "other"


def _priority(candidate: FeedCandidate) -> int:
    score = ORIGIN_PRIORITY.get(candidate.origin, 40)
    tags = {t.lower() for t in candidate.tags}
    url = candidate.url.lower()
    path = str(candidate.metadata.get("path") or "").lower()
    haystack = f"{url} {path}"

    if "auto" in tags and candidate.origin == "repository_tree":
        score += 14
    if "auto" in tags and candidate.origin == "github_repo_seed":
        score -= 45
    if "telegram" in tags:
        score += 10
    if "repository-tree" in tags:
        score += 8
    if "tested" in haystack:
        score += 28
    if "proxy_configs_tested" in haystack:
        score += 18

    for i, hint in enumerate(GOOD_PATH_HINTS):
        if hint in haystack:
            score += max(4, 22 - i)
            break
    for hint in BAD_PATH_HINTS:
        if hint in haystack:
            score -= 40
            break

    if url.endswith((".txt", ".yaml", ".yml", ".json")):
        score += 4
    if "raw.githubusercontent.com" in url:
        score += 3
    return score


def prioritize_candidates(candidates: list[FeedCandidate]) -> list[FeedCandidate]:
    by_url: dict[str, FeedCandidate] = {}
    for candidate in candidates:
        by_url.setdefault(candidate.url, candidate)
    deduped = list(by_url.values())
    return sorted(deduped, key=lambda c: (-_priority(c), _group(c), c.label, c.url))


def select_live_candidates(
    candidates: list[FeedCandidate],
    *,
    max_candidates: int,
    scan_limit: int | None = None,
    batch_size: int = 50,
) -> tuple[list[FeedCandidate], list[DeadPath], dict[str, Any]]:
    ordered = prioritize_candidates(candidates)
    limit = len(ordered) if scan_limit is None else min(len(ordered), max(scan_limit, max_candidates))
    alive: list[FeedCandidate] = []
    dead: list[DeadPath] = []
    scanned = 0

    while len(alive) < max_candidates and scanned < limit:
        batch = ordered[scanned : min(scanned + batch_size, limit)]
        if not batch:
            break
        batch_alive, batch_dead = preflight_candidates(batch)
        alive.extend(batch_alive)
        dead.extend(batch_dead)
        scanned += len(batch)

    selected = alive[:max_candidates]
    diagnostics: dict[str, Any] = {
        "raw_candidates": len(candidates),
        "deduped_candidates": len(ordered),
        "preflight_scanned": scanned,
        "preflight_alive": len(alive),
        "preflight_dead": len(dead),
        "selected": len(selected),
        "raw_groups": dict(Counter(_group(c) for c in candidates)),
        "selected_groups": dict(Counter(_group(c) for c in selected)),
        "top_queue": [
            {
                "label": c.label,
                "url": c.url,
                "origin": c.origin,
                "group": _group(c),
                "priority": _priority(c),
                "tags": c.tags,
                "metadata": c.metadata,
            }
            for c in ordered[: min(80, len(ordered))]
        ],
    }
    return selected, dead, diagnostics

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .models import FeedReport
from .utils import dedupe_keep_order, write_json

DEFAULT_PUBLIC_REPO = "mehdimt1980/v2ray-source-hunter"
DEFAULT_PUBLIC_BRANCH = "main"


def _is_telegram_report(report: FeedReport) -> bool:
    tags = {tag.lower() for tag in report.candidate.tags}
    return report.candidate.origin == "telegram_discovered_link" or (
        "telegram" in tags and "t.me/" in report.candidate.url
    )


def _public_repo() -> str:
    return os.environ.get("HUNTER_PUBLIC_REPO", DEFAULT_PUBLIC_REPO).strip() or DEFAULT_PUBLIC_REPO


def _public_branch() -> str:
    return os.environ.get("HUNTER_PUBLIC_BRANCH", DEFAULT_PUBLIC_BRANCH).strip() or DEFAULT_PUBLIC_BRANCH


def _raw_url(rel_path: str) -> str:
    return f"https://raw.githubusercontent.com/{_public_repo()}/{_public_branch()}/{rel_path}"


def _generated_filename(report: FeedReport) -> str:
    # FeedCandidate.id is already URL-safe and stable. Keeping it stable makes the
    # generated raw subscription URL stable across runs as long as the upstream
    # Telegram page URL stays the same.
    return f"{report.candidate.id}.txt"


def materialize_telegram_feeds(
    registry_dir: Path,
    reports: list[FeedReport],
    configs_by_url: dict[str, list[str]],
) -> list[dict[str, Any]]:
    generated_dir = registry_dir / "generated" / "telegram"
    generated_dir.mkdir(parents=True, exist_ok=True)

    # Remove stale generated subscriptions from older runs. GitHub Actions commits
    # the whole registry directory, so deletions are propagated too.
    for old_file in generated_dir.glob("*.txt"):
        old_file.unlink()

    manifest: list[dict[str, Any]] = []
    for report in reports:
        if report.status != "trusted" or not _is_telegram_report(report):
            continue

        source_url = report.candidate.url
        configs = dedupe_keep_order(configs_by_url.get(source_url, []))
        if not configs:
            continue

        filename = _generated_filename(report)
        rel_path = f"registry/generated/telegram/{filename}"
        out_path = generated_dir / filename
        out_path.write_text("\n".join(configs) + "\n", encoding="utf-8")

        public_url = _raw_url(rel_path)
        report.candidate.metadata = dict(report.candidate.metadata or {})
        report.candidate.metadata.update(
            {
                "original_url": source_url,
                "generated_subscription_path": rel_path,
                "generated_subscription_url": public_url,
                "generated_subscription_items": len(configs),
            }
        )

        if "generated-feed" not in report.candidate.tags:
            report.candidate.tags.append("generated-feed")

        manifest.append(
            {
                "id": report.candidate.id,
                "label": report.candidate.label,
                "source_url": source_url,
                "generated_path": rel_path,
                "generated_url": public_url,
                "items": len(configs),
                "score": report.score,
                "tcp_success_rate": report.tcp_success_rate,
                "protocols": report.protocols,
            }
        )

    write_json(registry_dir / "generated_telegram_feeds.json", manifest)
    return manifest

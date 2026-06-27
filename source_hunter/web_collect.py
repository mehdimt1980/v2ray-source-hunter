from __future__ import annotations

from pathlib import Path

from .models import FeedCandidate
from .utils import read_json, stable_id


def collect_web_candidates(path: Path) -> list[FeedCandidate]:
    raw = read_json(path, [])
    out: list[FeedCandidate] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        label = str(item.get("label") or url)
        out.append(
            FeedCandidate(
                id=stable_id(url),
                label=label,
                url=url,
                origin="web_seed",
                tags=["web"] + [str(t) for t in item.get("tags", [])],
                metadata={"source": "web_pages.json"},
            )
        )
    return out

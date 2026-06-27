from __future__ import annotations

from pathlib import Path

from .models import FeedCandidate
from .utils import read_json, stable_id


def collect_telegram_candidates(path: Path) -> list[FeedCandidate]:
    raw = read_json(path, [])
    out: list[FeedCandidate] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        channel = str(item.get("channel") or item.get("username") or "").strip().lstrip("@")
        if not channel:
            continue
        url = f"https://t.me/s/{channel}"
        label = str(item.get("label") or f"Telegram public channel {channel}")
        out.append(
            FeedCandidate(
                id=stable_id(url),
                label=label,
                url=url,
                origin="telegram_public_web",
                tags=["telegram", "public"] + [str(t) for t in item.get("tags", [])],
                metadata={"channel": channel, "access": "public_web"},
            )
        )
    return out

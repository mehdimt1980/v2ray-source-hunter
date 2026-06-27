from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class FeedCandidate:
    id: str
    label: str
    url: str
    origin: str
    kind: str = "public_feed"
    tags: list[str] = field(default_factory=list)
    discovered_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FeedReport:
    candidate: FeedCandidate
    fetch_ok: bool = False
    http_status: int | None = None
    error: str = ""
    raw_items: int = 0
    unique_items: int = 0
    duplicate_ratio: float = 0.0
    protocols: dict[str, int] = field(default_factory=dict)
    tcp_sample_size: int = 0
    tcp_ok_count: int = 0
    tcp_success_rate: float = 0.0
    score: float = 0.0
    status: str = "rejected"
    notes: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["candidate"] = self.candidate.to_dict()
        return data


@dataclass
class HunterResult:
    generated_at: str
    raw_candidates: int
    evaluated: int
    trusted: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    experimental: list[dict[str, Any]] = field(default_factory=list)
    redundant: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    dead_paths: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

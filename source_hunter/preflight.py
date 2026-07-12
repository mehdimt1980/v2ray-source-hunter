from __future__ import annotations

from dataclasses import asdict, dataclass

import requests

from .http_client import HEADERS
from .models import FeedCandidate
from .utils import is_valid_http_url, salvage_http_url


@dataclass
class DeadPath:
    url: str
    label: str
    origin: str
    status_code: int | None
    error: str

    def to_dict(self) -> dict:
        return asdict(self)


def preflight_candidates(candidates: list[FeedCandidate], *, timeout: float = 10.0) -> tuple[list[FeedCandidate], list[DeadPath]]:
    alive: list[FeedCandidate] = []
    dead: list[DeadPath] = []
    for candidate in candidates:
        if not is_valid_http_url(candidate.url):
            salvaged = salvage_http_url(candidate.url)
            if salvaged:
                candidate = FeedCandidate(
                    id=candidate.id,
                    label=candidate.label,
                    url=salvaged,
                    origin=candidate.origin,
                    kind=candidate.kind,
                    tags=candidate.tags,
                    discovered_at=candidate.discovered_at,
                    metadata={**candidate.metadata, "original_malformed_url": candidate.url},
                )
            else:
                dead.append(DeadPath(candidate.url, candidate.label, candidate.origin, None, "invalid_url"))
                continue
        try:
            response = requests.get(candidate.url, headers=HEADERS, timeout=timeout, stream=True)
            ok = response.status_code < 400
            if ok:
                alive.append(candidate)
            else:
                dead.append(DeadPath(candidate.url, candidate.label, candidate.origin, response.status_code, response.text[:200]))
        except Exception as exc:
            dead.append(DeadPath(candidate.url, candidate.label, candidate.origin, None, str(exc)))
    return alive, dead

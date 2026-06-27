from __future__ import annotations

from dataclasses import dataclass

import requests


@dataclass
class FetchResult:
    url: str
    ok: bool
    status_code: int | None
    text: str
    error: str = ""


HEADERS = {"User-Agent": "source-hunter/0.1"}


def fetch_text(url: str, *, timeout: float = 20.0) -> FetchResult:
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        return FetchResult(
            url=url,
            ok=response.ok and bool(response.text.strip()),
            status_code=response.status_code,
            text=response.text,
            error="" if response.ok else response.text[:300],
        )
    except Exception as exc:
        return FetchResult(url=url, ok=False, status_code=None, text="", error=str(exc))

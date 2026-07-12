from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import ParseResult, urlparse


DOMAIN_RE = re.compile(
    r"(?P<domain>(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63})(?P<path>/[^\s\"'<>]*)?",
    re.IGNORECASE,
)


def stable_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:72]
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{digest}" if slug else digest


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def dedupe_keep_order(items: list[str]) -> list[str]:
    return list(dict.fromkeys([x for x in items if x]))


def safe_urlparse(value: str) -> ParseResult | None:
    try:
        return urlparse((value or "").strip())
    except (ValueError, UnicodeError):
        return None


def is_valid_http_url(value: str) -> bool:
    parsed = safe_urlparse(value)
    if parsed is None:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def salvage_http_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if is_valid_http_url(raw):
        return raw
    match = DOMAIN_RE.search(raw.replace("：", ":"))
    if not match:
        return ""
    path = match.group("path") or ""
    candidate = "https://" + match.group("domain") + path
    return candidate if is_valid_http_url(candidate) else ""

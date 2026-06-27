from __future__ import annotations

import html
import re
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

from .http_client import fetch_text
from .models import FeedCandidate
from .utils import read_json, stable_id

HREF_RE = re.compile(r"href=[\"']([^\"']+)[\"']", re.IGNORECASE)
GITHUB_BLOB_RE = re.compile(r"^/([^/]+/[^/]+)/blob/([^/]+)/(.+)$")
GITHUB_FULL_BLOB_RE = re.compile(r"^https://github\.com/([^/]+/[^/]+)/blob/([^/]+)/(.+)$")
TELEGRAM_MESSAGE_RE = re.compile(r"^https://t\.me/[^/]+/\d+(?:\?.*)?$", re.IGNORECASE)

FEED_EXTENSIONS = (".txt", ".yaml", ".yml", ".json", ".conf", ".list")
FEED_KEYWORDS = (
    "v2ray",
    "vless",
    "vmess",
    "trojan",
    "shadowsocks",
    "ss://",
    "subscription",
    "subscribe",
    "sub",
    "config",
    "configs",
    "proxy",
    "proxies",
    "clash",
)


def _channel_page_url(channel: str) -> str:
    return f"https://t.me/s/{channel}"


def _normalize_url(url: str, *, base_url: str) -> str:
    value = html.unescape(unquote((url or "").strip()))
    if not value:
        return ""
    if value.startswith("tg://") or value.startswith("javascript:") or value.startswith("mailto:"):
        return ""
    if value.startswith("//"):
        value = "https:" + value
    elif value.startswith("/"):
        value = urljoin(base_url, value)

    blob_match = GITHUB_BLOB_RE.match(urlparse(value).path)
    if urlparse(value).netloc.lower() == "github.com" and blob_match:
        repo, ref, path = blob_match.groups()
        return f"https://raw.githubusercontent.com/{repo}/{ref}/{path}"

    full_blob_match = GITHUB_FULL_BLOB_RE.match(value)
    if full_blob_match:
        repo, ref, path = full_blob_match.groups()
        return f"https://raw.githubusercontent.com/{repo}/{ref}/{path}"

    return value


def _hrefs(text: str, *, base_url: str) -> list[str]:
    out: list[str] = []
    for href in HREF_RE.findall(text or ""):
        normalized = _normalize_url(href, base_url=base_url)
        if normalized:
            out.append(normalized)
    return list(dict.fromkeys(out))


def _looks_like_feed_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    query = parsed.query.lower()
    whole = f"{host}{path}?{query}"

    if host == "raw.githubusercontent.com":
        return True
    if host == "github.com":
        return "/blob/" in path and path.endswith(FEED_EXTENSIONS)
    if host in {"gist.githubusercontent.com", "pastebin.com", "rentry.co"}:
        return True
    if path.endswith(FEED_EXTENSIONS):
        return True
    if any(keyword in whole for keyword in FEED_KEYWORDS):
        return True
    return False


def _looks_crawlable(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if not host or TELEGRAM_MESSAGE_RE.match(url):
        return False
    if host in {"github.com", "gitlab.com"}:
        return True
    if host == "raw.githubusercontent.com":
        return False
    if host.endswith("t.me"):
        return False
    return any(keyword in (parsed.path + "?" + parsed.query).lower() for keyword in FEED_KEYWORDS)


def _candidate_from_url(
    url: str,
    *,
    channel: str,
    parent_url: str,
    label_prefix: str,
    tags: list[str],
) -> FeedCandidate:
    parsed = urlparse(url)
    short = parsed.netloc + parsed.path
    if len(short) > 80:
        short = short[:77] + "..."
    return FeedCandidate(
        id=stable_id(url),
        label=f"{label_prefix} → {short}",
        url=url,
        origin="telegram_discovered_link",
        tags=list(dict.fromkeys(["telegram", "discovered-link"] + tags)),
        metadata={"channel": channel, "parent_url": parent_url, "source": "telegram_web_link"},
    )


def _discover_link_candidates(
    page_url: str,
    *,
    channel: str,
    label_prefix: str,
    tags: list[str],
    timeout: float,
    max_links: int,
) -> list[FeedCandidate]:
    fetched = fetch_text(page_url, timeout=timeout)
    if not fetched.ok:
        return []

    candidates: list[FeedCandidate] = []
    seen: set[str] = set()
    crawl_queue: list[str] = []

    for url in _hrefs(fetched.text, base_url=page_url):
        if _looks_like_feed_url(url):
            if url not in seen:
                seen.add(url)
                candidates.append(
                    _candidate_from_url(url, channel=channel, parent_url=page_url, label_prefix=label_prefix, tags=tags)
                )
        elif _looks_crawlable(url):
            crawl_queue.append(url)
        if len(candidates) >= max_links:
            return candidates

    # One shallow crawl catches GitHub README pages or public subscription landing
    # pages linked from Telegram posts without turning the hunter into a broad web crawler.
    for crawl_url in list(dict.fromkeys(crawl_queue))[:8]:
        crawled = fetch_text(crawl_url, timeout=timeout)
        if not crawled.ok:
            continue
        for url in _hrefs(crawled.text, base_url=crawl_url):
            if not _looks_like_feed_url(url) or url in seen:
                continue
            seen.add(url)
            candidates.append(
                _candidate_from_url(url, channel=channel, parent_url=crawl_url, label_prefix=label_prefix, tags=tags)
            )
            if len(candidates) >= max_links:
                return candidates

    return candidates


def collect_telegram_candidates(path: Path, *, max_discovered_per_channel: int = 20, timeout: float = 12.0) -> list[FeedCandidate]:
    raw = read_json(path, [])
    out: list[FeedCandidate] = []
    seen_urls: set[str] = set()

    for item in raw:
        if not isinstance(item, dict):
            continue
        channel = str(item.get("channel") or item.get("username") or "").strip().lstrip("@")
        if not channel:
            continue

        url = _channel_page_url(channel)
        label = str(item.get("label") or f"Telegram public channel {channel}")
        tags = [str(t) for t in item.get("tags", [])]

        channel_candidate = FeedCandidate(
            id=stable_id(url),
            label=label,
            url=url,
            origin="telegram_public_web",
            tags=list(dict.fromkeys(["telegram", "public"] + tags)),
            metadata={"channel": channel, "access": "public_web"},
        )
        out.append(channel_candidate)
        seen_urls.add(url)

        if item.get("discover_links", True):
            for candidate in _discover_link_candidates(
                url,
                channel=channel,
                label_prefix=label,
                tags=tags,
                timeout=timeout,
                max_links=max_discovered_per_channel,
            ):
                if candidate.url in seen_urls:
                    continue
                seen_urls.add(candidate.url)
                out.append(candidate)

    return out

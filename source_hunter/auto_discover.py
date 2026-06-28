from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from .http_client import HEADERS, fetch_text
from .utils import read_json, write_json

EN_REPO_QUERIES = [
    "v2ray configs",
    "vless vmess trojan",
    "xray config subscription",
    "clash vless vmess",
]

ZH_DISCOVERY_TERMS = [
    "免费节点",
    "科学上网",
    "翻墙",
    "节点订阅",
    "机场",
    "每日更新",
]

ZH_PROTOCOL_TERMS = [
    "v2ray",
    "xray",
    "vless",
    "vmess",
    "trojan",
    "clash",
    "mihomo",
    "sing-box",
    "Shadowrocket",
]

ZH_FILENAME_TERMS = [
    "clash.yaml",
    "sub.yaml",
    "subscribe.txt",
    "nodes.txt",
    "v2ray.txt",
]


def _build_repo_queries() -> list[dict[str, Any]]:
    queries: list[dict[str, Any]] = []
    for query in EN_REPO_QUERIES:
        queries.append(
            {
                "query": query,
                "language_hint": "en",
                "region_hint": "global",
                "tags": ["auto", "github", "english"],
            }
        )

    # Chinese public-config repositories often use local terms instead of
    # English phrases such as "free v2ray config".  These combinations target
    # GitHub repositories maintained for users facing the Great Firewall, while
    # still using only public GitHub search and public repository metadata.
    seen: set[str] = {str(row["query"]).lower() for row in queries}
    for term in ZH_DISCOVERY_TERMS:
        for protocol in ZH_PROTOCOL_TERMS:
            query = f'{term} {protocol}'
            key = query.lower()
            if key not in seen:
                seen.add(key)
                queries.append(
                    {
                        "query": query,
                        "language_hint": "zh",
                        "region_hint": "cn",
                        "tags": ["auto", "github", "zh", "chinese", "github_zh_search"],
                        "matched_terms": [term, protocol],
                    }
                )
    for term in ZH_DISCOVERY_TERMS:
        for filename in ZH_FILENAME_TERMS:
            query = f'{term} {filename}'
            key = query.lower()
            if key not in seen:
                seen.add(key)
                queries.append(
                    {
                        "query": query,
                        "language_hint": "zh",
                        "region_hint": "cn",
                        "tags": ["auto", "github", "zh", "chinese", "github_zh_search", "filename_hint"],
                        "matched_terms": [term, filename],
                    }
                )
    return queries


REPO_QUERIES = _build_repo_queries()

TG_RE = re.compile(r"https?://t\.me/(?:s/)?([A-Za-z0-9_]{5,})", re.IGNORECASE)
TG_SKIP = {"share", "joinchat", "addstickers", "proxy", "iv", "c"}


def _github_headers() -> dict[str, str]:
    headers = dict(HEADERS)
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    headers["Accept"] = "application/vnd.github+json"
    return headers


def _github_get(url: str, *, params: dict[str, Any] | None = None, timeout: float = 20.0) -> dict[str, Any]:
    try:
        response = requests.get(url, params=params, headers=_github_headers(), timeout=timeout)
        if not response.ok:
            return {}
        data = response.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _merge_records(existing: list[dict[str, Any]], discovered: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in existing + discovered:
        if not isinstance(row, dict):
            continue
        value = str(row.get(key) or "").strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(row)
    return out


def _query_text(query_record: dict[str, Any] | str) -> str:
    if isinstance(query_record, dict):
        return str(query_record.get("query") or "").strip()
    return str(query_record or "").strip()


def _query_tags(query_record: dict[str, Any] | str) -> list[str]:
    if isinstance(query_record, dict):
        tags = query_record.get("tags") or []
        return [str(tag) for tag in tags if str(tag).strip()]
    return ["auto", "github"]


def _query_metadata(query_record: dict[str, Any] | str) -> dict[str, Any]:
    if not isinstance(query_record, dict):
        return {}
    metadata: dict[str, Any] = {}
    for key in ("language_hint", "region_hint", "matched_terms"):
        value = query_record.get(key)
        if value:
            metadata[key] = value
    return metadata


def _discover_repositories(*, per_query: int = 8, max_total: int = 30) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for query_record in REPO_QUERIES:
        query = _query_text(query_record)
        if not query:
            continue
        data = _github_get(
            "https://api.github.com/search/repositories",
            params={"q": query, "sort": "updated", "order": "desc", "per_page": per_query},
        )
        for item in data.get("items") or []:
            if not isinstance(item, dict):
                continue
            full_name = str(item.get("full_name") or "").strip()
            if not full_name or full_name.lower() in seen:
                continue
            seen.add(full_name.lower())
            branch = str(item.get("default_branch") or "main")
            metadata = {
                "stars": item.get("stargazers_count", 0),
                "updated_at": item.get("updated_at"),
                "discovery_query": query,
                "discovery_provider": "github_repository_search",
            }
            metadata.update(_query_metadata(query_record))
            found.append(
                {
                    "repository": full_name,
                    "branch": branch,
                    "tags": _query_tags(query_record),
                    "metadata": metadata,
                }
            )
            if len(found) >= max_total:
                return found
    return found


def _readme_text(repository: str) -> str:
    owner_repo = quote(repository, safe="/")
    data = _github_get(f"https://api.github.com/repos/{owner_repo}/readme")
    url = str(data.get("download_url") or "")
    if not url:
        return ""
    fetched = fetch_text(url, timeout=15.0)
    return fetched.text if fetched.ok else ""


def _telegram_channels_from_text(text: str) -> list[str]:
    out: list[str] = []
    for match in TG_RE.finditer(text or ""):
        channel = match.group(1).strip().lstrip("@").lower()
        if not channel or channel in TG_SKIP:
            continue
        out.append(channel)
    return list(dict.fromkeys(out))


def _is_public_tg_channel(channel: str) -> bool:
    fetched = fetch_text(f"https://t.me/s/{channel}", timeout=12.0)
    if not fetched.ok:
        return False
    body = fetched.text or ""
    return "tgme_widget_message" in body or "tgme_channel_history" in body


def _discover_telegram_channels(repositories: list[dict[str, Any]], *, max_total: int = 30) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for repo in repositories:
        repository = str(repo.get("repository") or "")
        if not repository:
            continue
        for channel in _telegram_channels_from_text(_readme_text(repository)):
            if channel in seen:
                continue
            seen.add(channel)
            if not _is_public_tg_channel(channel):
                continue
            found.append(
                {
                    "channel": channel,
                    "label": f"Telegram public channel {channel}",
                    "tags": ["auto", "telegram"],
                    "discover_links": True,
                    "metadata": {"discovered_from_repository": repository},
                }
            )
            if len(found) >= max_total:
                return found
    return found


def run_auto_discovery(
    registry_dir: Path,
    *,
    max_repositories: int = 30,
    max_channels: int = 30,
) -> dict[str, Any]:
    registry_dir.mkdir(parents=True, exist_ok=True)

    repositories = _discover_repositories(max_total=max_repositories)
    repositories_path = registry_dir / "discovered_repositories.json"
    repositories = _merge_records(read_json(repositories_path, []), repositories, "repository")
    write_json(repositories_path, repositories)

    telegram_channels = _discover_telegram_channels(repositories, max_total=max_channels)
    telegram_path = registry_dir / "discovered_telegram_channels.json"
    telegram_channels = _merge_records(read_json(telegram_path, []), telegram_channels, "channel")
    write_json(telegram_path, telegram_channels)

    report = {
        "repositories": len(repositories),
        "telegram_channels": len(telegram_channels),
        "repo_query_count": len(REPO_QUERIES),
        "zh_repo_query_count": sum(1 for row in REPO_QUERIES if isinstance(row, dict) and row.get("language_hint") == "zh"),
    }
    write_json(registry_dir / "discovery_report.json", report)
    return report

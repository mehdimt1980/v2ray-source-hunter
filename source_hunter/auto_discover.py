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

MULTILINGUAL_DISCOVERY_FAMILIES = [
    {
        "language_hint": "fa",
        "region_hint": "ir",
        "label": "persian",
        "terms": [
            "\u0641\u06cc\u0644\u062a\u0631\u0634\u06a9\u0646",
            "\u06a9\u0627\u0646\u0641\u06cc\u06af \u0631\u0627\u06cc\u06af\u0627\u0646",
            "\u0646\u0627\u062f \u0631\u0627\u06cc\u06af\u0627\u0646",
            "\u0627\u06cc\u0646\u062a\u0631\u0646\u062a \u0622\u0632\u0627\u062f",
            "\u0627\u067e\u062f\u06cc\u062a \u0631\u0648\u0632\u0627\u0646\u0647",
        ],
        "protocols": ["v2ray", "xray", "vless", "vmess", "trojan", "clash", "hiddify"],
    },
    {
        "language_hint": "ru",
        "region_hint": "ru",
        "label": "russian",
        "terms": [
            "\u0431\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u044b\u0435 \u043d\u043e\u0434\u044b",
            "\u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0430",
            "\u043a\u043e\u043d\u0444\u0438\u0433\u0438",
            "\u043e\u0431\u0445\u043e\u0434 \u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u043e\u043a",
        ],
        "protocols": ["v2ray", "xray", "vless", "vmess", "trojan", "clash"],
    },
    {
        "language_hint": "ar",
        "region_hint": "mena",
        "label": "arabic",
        "terms": [
            "\u0646\u0648\u062f\u0627\u062a \u0645\u062c\u0627\u0646\u064a\u0629",
            "\u0627\u0634\u062a\u0631\u0627\u0643",
            "\u0643\u0648\u0646\u0641\u064a\u062c",
            "\u062a\u062e\u0637\u064a \u0627\u0644\u062d\u062c\u0628",
        ],
        "protocols": ["v2ray", "xray", "vless", "vmess", "trojan", "clash"],
    },
    {
        "language_hint": "tr",
        "region_hint": "tr",
        "label": "turkish",
        "terms": [
            "ucretsiz node",
            "bedava config",
            "abonelik",
            "gunluk guncel",
        ],
        "protocols": ["v2ray", "xray", "vless", "vmess", "trojan", "clash"],
    },
]

MULTILINGUAL_FILENAME_TERMS = [
    "sub.txt",
    "subscription.txt",
    "subscribe.txt",
    "nodes.txt",
    "all.txt",
    "all_configs.txt",
    "v2ray.txt",
    "vless.txt",
    "vmess.txt",
    "trojan.txt",
    "clash.yaml",
    "mihomo.yaml",
    "sing-box.json",
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
    for family in MULTILINGUAL_DISCOVERY_FAMILIES:
        language_hint = str(family["language_hint"])
        region_hint = str(family["region_hint"])
        label = str(family["label"])
        tags = ["auto", "github", language_hint, label, "multilingual"]
        for term in family["terms"]:
            for protocol in family["protocols"]:
                query = f"{term} {protocol}"
                key = query.lower()
                if key in seen:
                    continue
                seen.add(key)
                queries.append(
                    {
                        "query": query,
                        "language_hint": language_hint,
                        "region_hint": region_hint,
                        "tags": tags,
                        "matched_terms": [term, protocol],
                    }
                )
        for term in family["terms"]:
            for filename in MULTILINGUAL_FILENAME_TERMS:
                query = f"{term} {filename}"
                key = query.lower()
                if key in seen:
                    continue
                seen.add(key)
                queries.append(
                    {
                        "query": query,
                        "language_hint": language_hint,
                        "region_hint": region_hint,
                        "tags": tags + ["filename_hint"],
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


def _query_counts_by_language() -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in REPO_QUERIES:
        language = (
            str(row.get("language_hint") or "unknown")
            if isinstance(row, dict)
            else "unknown"
        )
        counts[language] = counts.get(language, 0) + 1
    return dict(sorted(counts.items()))


def _query_language(query_record: dict[str, Any] | str) -> str:
    if isinstance(query_record, dict):
        return str(query_record.get("language_hint") or "unknown")
    return "unknown"


def _group_queries_by_language() -> dict[str, list[dict[str, Any] | str]]:
    grouped: dict[str, list[dict[str, Any] | str]] = {}
    for row in REPO_QUERIES:
        language = _query_language(row)
        grouped.setdefault(language, []).append(row)
    return grouped


def _discover_repositories(
    *,
    per_query: int = 8,
    max_total: int = 30,
    max_queries_per_language: int = 24,
    max_query_attempts: int = 120,
) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    grouped_queries = _group_queries_by_language()
    language_quota = max(2, max_total // max(1, len(grouped_queries)))
    language_counts = {language: 0 for language in grouped_queries}
    query_attempts = 0

    def search_query(
        query_record: dict[str, Any] | str,
        *,
        language: str,
        enforce_quota: bool,
    ) -> bool:
        nonlocal found, query_attempts
        if len(found) >= max_total:
            return False
        if query_attempts >= max_query_attempts:
            return False
        if enforce_quota and language_counts.get(language, 0) >= language_quota:
            return True
        query = _query_text(query_record)
        if not query:
            return True
        query_attempts += 1
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
            if enforce_quota and language_counts.get(language, 0) >= language_quota:
                break
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
            language_counts[language] = language_counts.get(language, 0) + 1
            if len(found) >= max_total:
                return False
        return True

    for language in sorted(grouped_queries):
        for query_record in grouped_queries[language][:max_queries_per_language]:
            if not search_query(query_record, language=language, enforce_quota=True):
                return found
    for query_record in REPO_QUERIES:
        if not search_query(query_record, language=_query_language(query_record), enforce_quota=False):
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
        "zh_repo_query_count": sum(
            1
            for row in REPO_QUERIES
            if isinstance(row, dict) and row.get("language_hint") == "zh"
        ),
        "repo_query_count_by_language": _query_counts_by_language(),
    }
    write_json(registry_dir / "discovery_report.json", report)
    return report

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import requests

from .http_client import HEADERS
from .models import FeedCandidate
from .utils import read_json, stable_id

INTERESTING_EXT = (".txt", ".yaml", ".yml")
KEYWORDS = ("sub", "merge", "all", "config", "clash", "vless", "vmess", "trojan", "ss", "eternity")


def _tree_url(repo: str, branch: str) -> str:
    owner, name = repo.split("/", 1)
    return "https://api.github.com/repos/" + quote(owner) + "/" + quote(name) + "/git/trees/" + quote(branch) + "?recursive=1"


def _raw_url(repo: str, branch: str, path: str) -> str:
    return "https://raw.githubusercontent.com/" + repo + "/" + branch + "/" + path


def collect_repo_tree_candidates(path: Path, *, max_paths_per_repo: int = 20) -> list[FeedCandidate]:
    raw = read_json(path, [])
    out: list[FeedCandidate] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        repo = str(item.get("repository") or "").strip()
        branch = str(item.get("branch") or "main")
        if not repo or "/" not in repo:
            continue
        try:
            resp = requests.get(_tree_url(repo, branch), headers=HEADERS, timeout=20)
            if not resp.ok:
                continue
            tree = resp.json().get("tree") or []
        except Exception:
            continue
        paths: list[str] = []
        for node in tree:
            rel = str(node.get("path") or "")
            low = rel.lower()
            if node.get("type") != "blob":
                continue
            if not low.endswith(INTERESTING_EXT):
                continue
            if not any(k in low for k in KEYWORDS):
                continue
            paths.append(rel)
        for rel in paths[:max_paths_per_repo]:
            url = _raw_url(repo, branch, rel)
            out.append(
                FeedCandidate(
                    id=stable_id(url),
                    label=f"{repo} — {rel}",
                    url=url,
                    origin="repository_tree",
                    tags=["repository-tree"] + [str(t) for t in item.get("tags", [])],
                    metadata={"repository": repo, "branch": branch, "path": rel},
                )
            )
    return out

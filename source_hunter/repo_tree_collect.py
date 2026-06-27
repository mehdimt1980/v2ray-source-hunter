from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

import requests

from .http_client import HEADERS
from .models import FeedCandidate
from .utils import read_json, stable_id

INTERESTING_EXT = (".txt", ".yaml", ".yml")
PREFERRED_KEYWORDS = ("all_configs", "all-configs", "sub_merge", "sub-merge", "eternity", "clash", "config")
EXCLUDED_PARTS = (".github/", "workflow", "sub/list/", "readme", "license")
GENERATED_CHUNK_RE = re.compile(r"(?:config list|sub)\d+[_\-]base64", re.IGNORECASE)


def _tree_url(repo: str, branch: str) -> str:
    owner, name = repo.split("/", 1)
    return "https://api.github.com/repos/" + quote(owner) + "/" + quote(name) + "/git/trees/" + quote(branch) + "?recursive=1"


def _raw_url(repo: str, branch: str, path: str) -> str:
    return "https://raw.githubusercontent.com/" + repo + "/" + branch + "/" + path


def _path_rank(path: str) -> int:
    low = path.lower()
    if "all_configs" in low or "all-configs" in low:
        return 0
    if "sub_merge" in low or "sub-merge" in low:
        return 1
    if "eternity" in low:
        return 2
    if low.endswith(("clash.yaml", "clash.yml")):
        return 3
    if "config" in low:
        return 4
    return 9


def _keep_path(path: str) -> bool:
    low = path.lower()
    if not low.endswith(INTERESTING_EXT):
        return False
    if any(part in low for part in EXCLUDED_PARTS):
        return False
    if GENERATED_CHUNK_RE.search(low):
        return False
    return any(k in low for k in PREFERRED_KEYWORDS)


def collect_repo_tree_candidates(path: Path, *, max_paths_per_repo: int = 8) -> list[FeedCandidate]:
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
            if node.get("type") == "blob" and _keep_path(rel):
                paths.append(rel)
        for rel in sorted(set(paths), key=_path_rank)[:max_paths_per_repo]:
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

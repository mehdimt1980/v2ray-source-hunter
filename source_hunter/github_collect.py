from __future__ import annotations

from pathlib import Path

from .models import FeedCandidate
from .utils import read_json, stable_id

COMMON_PATHS = [
    "sub.txt",
    "all.txt",
    "all_configs.txt",
    "All_Configs_Sub.txt",
    "Eternity.txt",
    "subscribe.txt",
    "subscription.txt",
    "nodes.txt",
    "v2ray.txt",
    "vless.txt",
    "vmess.txt",
    "trojan.txt",
    "ss.txt",
    "clash.yaml",
    "clash.yml",
    "mihomo.yaml",
    "mihomo.yml",
    "sing-box.json",
    "singbox.json",
    "shadowrocket.txt",
]


def collect_github_repo_candidates(path: Path) -> list[FeedCandidate]:
    raw = read_json(path, [])
    out: list[FeedCandidate] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        repo = str(item.get("repository") or "").strip()
        if not repo or "/" not in repo:
            continue
        branch = str(item.get("branch") or "main")
        paths = item.get("paths") or COMMON_PATHS
        for rel in paths:
            rel = str(rel).strip().lstrip("/")
            if not rel:
                continue
            url = f"https://raw.githubusercontent.com/{repo}/{branch}/{rel}"
            label = f"{repo} — {rel}"
            out.append(
                FeedCandidate(
                    id=stable_id(url),
                    label=label,
                    url=url,
                    origin="github_repo_seed",
                    tags=["github"] + [str(t) for t in item.get("tags", [])],
                    metadata={"repository": repo, "branch": branch, "path": rel},
                )
            )
    return out
